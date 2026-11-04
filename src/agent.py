# Kulsh GPT | agent actions: contacts, cross-chat messages, owner alerts, refusals.

"""Small, explicit action layer for the bot's autonomous behaviour.

The language model only emits markers. This module performs the side effects:
looking up a person the bot has actually seen, enforcing per-chat permissions,
sending a DM, and notifying the owner. No marker can send to an arbitrary ID.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from src.util import DATA_DIR, PREMIUM_ADMIN_ID, logger

CONTACTS_FILE = os.path.join(DATA_DIR, "agent_contacts.json")
BLOCKS_FILE = os.path.join(DATA_DIR, "agent_blocks.json")
GROUPS_FILE = os.path.join(DATA_DIR, "agent_groups.json")

_last_notice: dict[str, float] = {}


def _load(path: str, default: Any) -> Any:
    try:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
    except Exception as exc:
        logger.warning(f"agent load {path}: {exc}")
    return default


def _save(path: str, value: Any) -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.warning(f"agent save {path}: {exc}")


_contacts: dict[str, dict[str, Any]] = _load(CONTACTS_FILE, {})
_blocks: set[str] = set(str(item) for item in _load(BLOCKS_FILE, []))
_groups: dict[str, dict[str, Any]] = _load(GROUPS_FILE, {})


def _key(platform: str, user_id: int) -> str:
    return f"{platform}:{int(user_id)}"


def remember_contact(platform: str, user_id: int, display: str, username: str = "",
                     is_private: bool = False, is_bot: bool = False) -> None:
    if not user_id:
        return
    key = _key(platform, user_id)
    entry = _contacts.setdefault(key, {})
    entry.update({
        "platform": platform,
        "id": int(user_id),
        "display": (display or username or str(user_id))[:120],
        "username": (username or "").lstrip("@")[:120],
        "private": bool(is_private or entry.get("private")),
        "is_bot": bool(is_bot or entry.get("is_bot")),
        "seen": int(time.time()),
    })
    _save(CONTACTS_FILE, _contacts)


def is_blocked(platform: str, user_id: int) -> bool:
    return _key(platform, user_id) in _blocks


def block_user(platform: str, user_id: int) -> None:
    _blocks.add(_key(platform, user_id))
    _save(BLOCKS_FILE, sorted(_blocks))


def unblock_user(platform: str, user_id: int) -> None:
    _blocks.discard(_key(platform, user_id))
    _save(BLOCKS_FILE, sorted(_blocks))


def group_setting(platform: str, chat_id: int, name: str, default: bool = False) -> bool:
    return bool((_groups.get(f"{platform}_{chat_id}") or {}).get(name, default))


def set_group_setting(platform: str, chat_id: int, name: str, value: bool) -> None:
    key = f"{platform}_{chat_id}"
    _groups.setdefault(key, {})[name] = bool(value)
    _save(GROUPS_FILE, _groups)


def cross_chat_allowed(platform: str, chat_id: int, is_private: bool) -> bool:
    if is_private:
        return True
    return group_setting(platform, chat_id, "cross_chat_enabled", False)


def find_contacts(platform: str, query: str) -> list[dict[str, Any]]:
    query = query.strip()
    if query.lower().startswith(("tg:", "ds:")):
        platform, query = query[:2].lower(), query[3:].strip()
    query = query.lstrip("@").casefold()
    if not query:
        return []
    exact: list[dict[str, Any]] = []
    partial: list[dict[str, Any]] = []
    for entry in _contacts.values():
        if entry.get("platform") != platform or entry.get("is_bot"):
            continue
        name = str(entry.get("display") or "").casefold()
        username = str(entry.get("username") or "").casefold()
        if query in (name, username):
            exact.append(entry)
        elif query in name or query in username:
            partial.append(entry)
    return exact or partial


async def send_dm(platform: str, user_id: int, text: str) -> bool:
    try:
        if platform == "tg":
            from src.telegram import tg_bot
            await tg_bot.send_message(int(user_id), text[:4000])
            return True
        if platform == "ds":
            from src.discord_cmds import ds_bot
            user = ds_bot.get_user(int(user_id))
            if user is None:
                user = await ds_bot.fetch_user(int(user_id))
            await user.send(text[:1900])
            return True
    except Exception as exc:
        logger.info(f"agent DM {platform}:{user_id} failed: {type(exc).__name__}: {exc}")
    return False


async def notify_owner(text: str, *, unblock: tuple[str, int] | None = None,
                       source: str = "") -> None:
    """Notify the owner in both messengers, with an unblock button in Telegram."""
    stamp = time.time()
    key = source or (f"{unblock[0]}:{unblock[1]}" if unblock else "")
    if key and stamp - _last_notice.get(key, 0) < 300:
        return
    _last_notice[key] = stamp
    body = text[:3500]
    try:
        from src.telegram import tg_bot
        markup = None
        if unblock is not None:
            from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(
                "Разблокировать", callback_data=f"adm:unblockbot:{unblock[0]}:{unblock[1]}",
            ))
        await tg_bot.send_message(PREMIUM_ADMIN_ID, body, reply_markup=markup)
    except Exception as exc:
        logger.warning(f"agent owner TG alert: {exc}")
    try:
        from src.billing import SUPPORT_ADMIN_DS
        from src.discord_cmds import ds_bot
        from src.util import AUTHORIZED_UPDATERS
        admin_id = SUPPORT_ADMIN_DS or (AUTHORIZED_UPDATERS[0] if AUTHORIZED_UPDATERS else 0)
        if admin_id:
            import discord
            user = ds_bot.get_user(int(admin_id)) or await ds_bot.fetch_user(int(admin_id))
            view = discord.ui.View(timeout=86400)
            if unblock is not None:
                button = discord.ui.Button(label="Разблокировать", style=discord.ButtonStyle.danger)

                async def _click(interaction: Any) -> None:
                    unblock_user(unblock[0], unblock[1])
                    await interaction.response.send_message("Пользователь разблокирован.", ephemeral=True)

                button.callback = _click
                view.add_item(button)
            await user.send(body[:1900], view=view if unblock is not None else None)
    except Exception as exc:
        logger.warning(f"agent owner DS alert: {exc}")


async def tell(platform: str, chat_id: int, is_private: bool, requester_id: int,
               query: str, text: str) -> str:
    """Resolve a person from the bot's actual contacts and send one private message."""
    from src.util import scrub_stray_markers
    text = scrub_stray_markers(text)
    if not cross_chat_allowed(platform, chat_id, is_private):
        return "в этом чате межчатовые сообщения выключены админом"
    if not query.strip() or not text.strip():
        return "не понял, кому и что отправить"
    target_platform = platform
    stripped_query = query.strip()
    if stripped_query.lower().startswith(("tg:", "ds:")):
        target_platform = stripped_query[:2].lower()
        query = stripped_query[3:].strip()
    matches = find_contacts(target_platform, query)
    unique = {str(item.get("id")): item for item in matches}
    if not unique:
        return f"не нашёл личного чата с «{query.strip()[:40]}». пусть человек сначала напишет боту в лс"
    if len(unique) > 1:
        return f"нашёл нескольких похожих на «{query.strip()[:40]}», уточни ник"
    contact = next(iter(unique.values()))
    ok = await send_dm(target_platform, int(contact["id"]), text)
    name = str(contact.get("display") or contact.get("username") or contact["id"])
    if ok:
        logger.info(f"agent tell {platform}:{requester_id} -> {target_platform}:{contact['id']}")
        return f"отправил {name} в лс"
    return f"не смог написать {name}: возможно, человек ещё не открывал лс с ботом"