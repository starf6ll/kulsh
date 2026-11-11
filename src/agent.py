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
    """Можно ли доставлять сообщения В этот чат из других чатов.

    Личка всегда открыта, группа/канал — по настройке её админов.
    """
    if is_private:
        return True
    return group_setting(platform, chat_id, "cross_chat_enabled", False)


def autonomous_allowed(platform: str, chat_id: int) -> bool:
    """Может ли бот писать в этот чат сам, без просьбы участников."""
    return group_setting(platform, chat_id, "autonomous_enabled", True)


OWNER_ALIASES = frozenset({
    "фолз", "фолзу", "фолза", "фолзе", "фоллз", "фоллзу", "фоллза", "фоллзе",
    "lolfall", "starf6ll", "starfall", "богдан", "богдану", "богдана",
})


def owner_id(platform: str) -> int:
    if platform == "tg":
        return int(PREMIUM_ADMIN_ID or 0)
    from src.billing import SUPPORT_ADMIN_DS
    from src.util import AUTHORIZED_UPDATERS
    return int(SUPPORT_ADMIN_DS or (AUTHORIZED_UPDATERS[0] if AUTHORIZED_UPDATERS else 0))


def find_contacts(platform: str, query: str) -> list[dict[str, Any]]:
    query = query.strip()
    if query.lower().startswith(("tg:", "ds:")):
        platform, query = query[:2].lower(), query[3:].strip()
    query = query.lstrip("@").casefold()
    if not query:
        return []
    if query in OWNER_ALIASES:
        oid = owner_id(platform)
        if oid:
            return [_contacts.get(_key(platform, oid)) or {
                "platform": platform, "id": oid, "display": "Фолз", "username": "lolfall",
            }]
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
    return await _send_text(platform, int(user_id), text, dm=True)


async def _ds_channel_targets(query: str, context_chat_id: int = 0) -> list[dict[str, Any]]:
    """Найти текстовые каналы Discord по названию среди серверов бота."""
    try:
        from src.discord_cmds import ds_bot
    except Exception:
        return []
    if ds_bot is None:
        return []
    needle = " ".join(query.strip().lstrip("@").casefold().replace("-", " ").replace("_", " ").split())
    if not needle:
        return []

    current_guilds: list[Any] = []
    other_guilds: list[Any] = []
    try:
        current = ds_bot.get_channel(int(context_chat_id)) if context_chat_id else None
        guild = getattr(current, "guild", None)
        if guild is not None:
            current_guilds.append(guild)
    except Exception:
        pass
    for guild in getattr(ds_bot, "guilds", []) or []:
        if guild not in current_guilds:
            other_guilds.append(guild)

    def _scan(guilds: list[Any]) -> list[dict[str, Any]]:
        exact: list[dict[str, Any]] = []
        partial: list[dict[str, Any]] = []
        for guild in guilds:
            for channel in getattr(guild, "text_channels", []) or []:
                try:
                    if not channel.permissions_for(guild.me).send_messages:
                        continue
                except Exception:
                    continue
                name = " ".join(str(getattr(channel, "name", "") or "").casefold()
                                .replace("-", " ").replace("_", " ").split())
                if not name:
                    continue
                entry = {
                    "platform": "ds", "id": int(channel.id), "kind": "channel",
                    "title": name, "guild_id": int(getattr(guild, "id", 0) or 0),
                }
                if needle == name:
                    exact.append(entry)
                elif needle in name:
                    partial.append(entry)
        return exact or partial

    # Сначала ищем на текущем сервере: так «секретный чат» не превращается
    # в одноимённый канал другого сервера или в Telegram-группу.
    found = _scan(current_guilds)
    return found or _scan(other_guilds)


async def find_targets(platform: str, query: str, context_chat_id: int = 0) -> list[dict[str, Any]]:
    """Люди из контактов и известные группы/каналы — всё, куда можно написать."""
    from src import chats
    targets = [{**item, "kind": "user"} for item in find_contacts(platform, query)]
    for entry in chats.find(platform, query):
        targets.append({**entry, "kind": "chat"})
    if platform == "ds":
        known = {int(item.get("id") or 0) for item in targets}
        for entry in await _ds_channel_targets(query, context_chat_id):
            if int(entry.get("id") or 0) not in known:
                targets.append({**entry, "kind": "chat"})
    return targets


async def _send_text(platform: str, chat_id: int, text: str, *, dm: bool = False) -> bool:
    if not (text or "").strip():
        return True
    try:
        if platform == "tg":
            from src.telegram import tg_bot
            await tg_bot.send_message(int(chat_id), text[:4000])
            return True
        if platform == "ds":
            from src.discord_cmds import ds_bot
            if dm:
                user = ds_bot.get_user(int(chat_id)) or await ds_bot.fetch_user(int(chat_id))
                await user.send(text[:1900])
            else:
                channel = ds_bot.get_channel(int(chat_id))
                if channel is None:
                    channel = await ds_bot.fetch_channel(int(chat_id))
                await channel.send(text[:1900])
            return True
    except Exception as exc:
        logger.info(f"agent send {platform}:{chat_id} failed: {type(exc).__name__}: {exc}")
    return False


async def _send_photo(platform: str, chat_id: int, png: bytes, caption: str = "",
                      *, dm: bool = False) -> bool:
    try:
        if platform == "tg":
            import io
            from telebot.types import InputFile
            from src.telegram import tg_bot
            await tg_bot.send_photo(
                int(chat_id), InputFile(io.BytesIO(png), file_name="drawing.png"),
                caption=(caption or "")[:1000],
            )
            return True
        if platform == "ds":
            import io
            import discord
            from src.discord_cmds import ds_bot
            file = discord.File(fp=io.BytesIO(png), filename="drawing.png")
            if dm:
                user = ds_bot.get_user(int(chat_id)) or await ds_bot.fetch_user(int(chat_id))
                await user.send(content=(caption or "")[:1900] or None, file=file)
            else:
                channel = ds_bot.get_channel(int(chat_id))
                if channel is None:
                    channel = await ds_bot.fetch_channel(int(chat_id))
                await channel.send(content=(caption or "")[:1900] or None, file=file)
            return True
    except Exception as exc:
        logger.info(f"agent photo {platform}:{chat_id} failed: {type(exc).__name__}: {exc}")
    return False


async def _outgoing_image(platform: str, chat_id: int, user_id: int,
                          spec: dict[str, Any] | None, prompt: str) -> bytes | None:
    """Картинка для межчатового/самостоятельного сообщения: !image, затем Paint."""
    from src.image_gen import generate_for_user, image_can_generate
    from src.util import get_effective_config
    cfg = get_effective_config(platform, chat_id, user_id)
    choice = cfg.get("image_model", "auto")
    if spec is not None and choice != "paint" and image_can_generate(platform, user_id, choice):
        try:
            png = await generate_for_user(platform, user_id, choice, spec, None)
            if png:
                return png
        except Exception as exc:
            logger.info(f"agent image {platform}:{chat_id}: {exc}")
    try:
        from src.ai import ask_paint
        from src.draw import process_drawing
        paint_prompt = ""
        if isinstance(spec, dict):
            paint_prompt = str(spec.get("prompt") or "").strip()
        paint_prompt = paint_prompt or prompt or "нарисуй картинку"
        raw = await ask_paint(paint_prompt, platform, chat_id, user_id)
        result = await process_drawing(raw or "")
        if result.png is not None:
            return result.png.getvalue()
    except Exception as exc:
        logger.info(f"agent paint {platform}:{chat_id}: {exc}")
    return None


async def deliver_message(platform: str, chat_id: int, text: str, *, user_id: int = 0,
                          dm: bool = False, clean_style: bool = False) -> bool:
    """Отправить сообщение, обработав !separate, !image и !draw."""
    from src.image_gen import extract_image_parts
    from src.util import extract_agent_actions, process_ai_response, scrub_stray_markers, take_reply_target

    def _clean(segment: str) -> str:
        segment = scrub_stray_markers(segment).strip()
        if clean_style:
            from src.util import strip_chat_emojis
            segment = strip_chat_emojis(segment)
        return segment

    # !tell/!notify_owner/!refuse не должны попадать в текст и не должны
    # перехватывать вложенный !image/!draw: иначе картинка уйдёт не в тот чат.
    text, _actions = extract_agent_actions(text or "")
    try:
        spec, before, after = extract_image_parts(text or "")
    except Exception:
        spec, before, after = None, text, ""
    body = before if spec is not None else (text or "")

    draw_png: bytes | None = None
    if "!draw" in body or "<svg" in body.lower():
        try:
            from src.draw import process_drawing
            result = await process_drawing(body)
            if result.png is not None:
                draw_png = result.png.getvalue()
                body = " ".join(part for part in (result.before, result.after) if part)
        except Exception as exc:
            logger.info(f"agent draw {platform}:{chat_id}: {exc}")

    segments, _markers = process_ai_response(body or "", separate_enabled=True)
    ok = True
    for segment in segments:
        segment, _reply_target = take_reply_target(segment)
        segment = _clean(segment)
        if segment:
            ok = await _send_text(platform, chat_id, segment, dm=dm) and ok

    caption = _clean(after or "")
    if spec is not None:
        png = await _outgoing_image(platform, chat_id, user_id, spec, before or text)
        if png:
            ok = await _send_photo(platform, chat_id, png, caption, dm=dm) and ok
    elif draw_png:
        ok = await _send_photo(platform, chat_id, draw_png, caption, dm=dm) and ok
    return ok


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


async def describe_tell(platform: str, chat_id: int, user_id: int, result: dict[str, Any]) -> str:
    """Let the model word the outcome of a tell action in the bot's own voice."""
    from src.ai import ask_ai_async
    facts = json.dumps(result, ensure_ascii=False)
    prompt = (
        "Ты только что выполнил просьбу передать сообщение. Результат действия "
        f"(JSON): {facts}. Коротко, своими словами, в своём стиле сообщи пользователю, что вышло. "
        "Если ok=false — объясни причину по-человечески: если reason=not_found — скажи, что не нашёл такой чат, "
        "и попроси точное название; если reason=ambiguous — попроси уточнить, какой из вариантов; если "
        "reason=cross_chat_disabled — скажи, что в этом чате выключен приём межчатовых сообщений, и предложи "
        "включить переключатель «Межчатовые сообщения»; если reason=send_failed или dm_failed — скажи, что "
        "не удалось отправить. "
        "Не пиши технических терминов и не упоминай JSON."
    )
    try:
        text = await ask_ai_async(prompt=prompt, context_type="default",
                                  chat_id=chat_id, user_id=user_id, platform=platform)
    except Exception as exc:
        logger.warning(f"agent describe_tell: {exc}")
        return ""
    return (text or "").strip()


async def tell(platform: str, chat_id: int, is_private: bool, requester_id: int,
               query: str, text: str) -> dict[str, Any]:
    """Передать сообщение человеку в личку или в другой чат.

    Возвращает структурированный результат: человеческую фразу формулирует модель.
    """
    text = text or ""
    if not query.strip() or not text.strip():
        return {"ok": False, "reason": "empty", "query": query.strip()[:40]}
    target_platform = platform
    stripped_query = query.strip()
    explicit_platform = stripped_query.lower().startswith(("tg:", "ds:"))
    if explicit_platform:
        target_platform = stripped_query[:2].lower()
        query = stripped_query[3:].strip()
    matches = await find_targets(
        target_platform, query,
        context_chat_id=chat_id if target_platform == platform else 0,
    )
    # Модель иногда по ошибке ставит чужой префикс (tg: в Discord). Если там
    # ничего не нашлось, пробуем текущую платформу, а не сдаёмся.
    if explicit_platform and target_platform != platform and not matches:
        fallback = await find_targets(platform, query, context_chat_id=chat_id)
        if fallback:
            target_platform = platform
            matches = fallback
    unique: dict[str, dict[str, Any]] = {}
    for item in matches:
        unique[f"{item.get('kind')}:{item.get('id')}"] = item
    if not unique:
        return {"ok": False, "reason": "not_found", "query": query.strip()[:40]}

    def _match_score(item: dict[str, Any]) -> int:
        q = query.strip().casefold()
        names = [
            str(item.get("display") or "").casefold(),
            str(item.get("title") or "").casefold(),
            str(item.get("username") or "").casefold(),
        ]
        if any(name and name == q for name in names):
            return 2
        if any(name and q in name for name in names):
            return 1
        return 0

    best_score = max(_match_score(item) for item in unique.values())
    if best_score > 0 and len(unique) > 1:
        unique = {key: item for key, item in unique.items() if _match_score(item) == best_score}
    if len(unique) > 1:
        names = [str(item.get("display") or item.get("title") or item.get("id"))[:40]
                 for item in unique.values()][:5]
        return {"ok": False, "reason": "ambiguous", "query": query.strip()[:40], "candidates": names}
    target = next(iter(unique.values()))
    target_id = int(target["id"])
    if target.get("kind") == "chat":
        name = str(target.get("title") or target_id)
        if not cross_chat_allowed("tg" if target.get("platform") == "tg" else "ds", target_id, False):
            return {"ok": False, "reason": "cross_chat_disabled", "name": name}
        ok = await deliver_message(target_platform, target_id, text, user_id=requester_id)
        logger.info(f"agent tell {platform}:{requester_id} -> chat {target_platform}:{target_id} ok={ok}")
        if ok:
            return {"ok": True, "name": name, "target": "chat"}
        return {"ok": False, "reason": "send_failed", "name": name, "target": "chat"}
    name = str(target.get("display") or target.get("username") or target_id)
    ok = await deliver_message(target_platform, target_id, text, user_id=requester_id, dm=True)
    if ok:
        logger.info(f"agent tell {platform}:{requester_id} -> {target_platform}:{target_id}")
        return {"ok": True, "name": name, "target": "dm"}
    return {"ok": False, "reason": "dm_failed", "name": name, "target": "dm"}
