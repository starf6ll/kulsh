# Kulsh GPT | v2.50.0
# by (main author): starfall-apk
# coauthor & bot hosting: pomidorka1515

"""Secret admin panel: stats, blocks, balance top-ups and exact broadcasts."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from datetime import datetime
from typing import Any

from src.billing import SUPPORT_ADMIN_DS, SUPPORT_ADMIN_TG, add_balance
from src.util import (
    AUTHORIZED_UPDATERS,
    MSK,
    PREMIUM_ADMIN_ID,
    logger,
    model_display_name,
    user_configs,
)

SECRET_COMMAND = "adminpanel12345"
USERS_FILE = "admin_users.json"
BLOCK_FILE = "blocked_users.json"
REQUESTS_FILE = "request_log.json"
CANCEL_WORDS = {"/cancel", "отмена", "cancel", "/отмена", "отменить"}

ADMIN_TG_IDS = {PREMIUM_ADMIN_ID, SUPPORT_ADMIN_TG}
ADMIN_DS_IDS = {uid for uid in AUTHORIZED_UPDATERS if uid} | ({SUPPORT_ADMIN_DS} if SUPPORT_ADMIN_DS else set())

_wait: dict[int, dict[str, Any]] = {}
_albums: dict[str, list[int]] = {}
_ds_albums: dict[str, list[Any]] = {}


def _load(path: str, default: Any) -> Any:
    try:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"{path} load fail: {e}")
    return default


def _save(path: str, data: Any) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"{path} save fail: {e}")


_users: dict[str, dict[str, dict[str, Any]]] = _load(USERS_FILE, {"tg": {}, "ds": {}})
_users.setdefault("tg", {})
_users.setdefault("ds", {})
_blocked: set[str] = set(str(x) for x in _load(BLOCK_FILE, []))
_requests: list[dict[str, Any]] = list(_load(REQUESTS_FILE, []))


def is_secret_command(text: str | None) -> bool:
    token = ((text or "").strip().split() or [""])[0].split("@", 1)[0].lstrip("/").lower()
    return token == SECRET_COMMAND


def is_admin_tg(user_id: int) -> bool:
    return user_id in ADMIN_TG_IDS


def is_admin_ds(user_id: int) -> bool:
    return user_id in ADMIN_DS_IDS


def is_blocked(platform: str, user_id: int) -> bool:
    return f"{platform}:{user_id}" in _blocked


def _prefix(name: str) -> str:
    cleaned = re.sub(r"\s+", "", name or "")
    cleaned = re.sub(r"[*_`\[\]]", "", cleaned)
    return cleaned[:2] or "—"


def touch_user(platform: str, user_id: int, name: str = "") -> None:
    if not user_id:
        return
    bucket = _users.setdefault(platform, {})
    entry = bucket.setdefault(str(user_id), {})
    if name:
        entry["p"] = _prefix(name)
    entry["seen"] = int(time.time())
    _save(USERS_FILE, _users)


def log_request(platform: str, user_id: int, model: str, tokens: int) -> None:
    if not user_id:
        return
    prefix = str((_users.get(platform) or {}).get(str(user_id), {}).get("p") or "—")
    _requests.append({
        "ts": int(time.time()),
        "platform": platform,
        "model": model,
        "tokens": int(tokens or 0),
        "p": prefix[:2],
    })
    del _requests[:-40]
    _save(REQUESTS_FILE, _requests)


def _known_ids(platform: str) -> set[int]:
    ids = {int(uid) for uid in (_users.get(platform) or {}) if str(uid).isdigit()}
    prefix = f"{platform}_"
    for key in user_configs:
        if not str(key).startswith(prefix):
            continue
        tail = str(key).rsplit("_", 1)[-1]
        if tail.isdigit() and tail != "0":
            ids.add(int(tail))
    return ids


def _fmt_tokens(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def home_text() -> str:
    tg_n = len(_known_ids("tg"))
    ds_n = len(_known_ids("ds"))
    lines = [
        "# 🛠 Админ-панель",
        "",
        "---",
        "",
        f"- **Telegram:** {tg_n}",
        f"- **Discord:** {ds_n}",
        f"- **В блоке:** {len(_blocked)}",
        "",
        "---",
        "",
        "**Последние запросы**",
        "",
    ]
    rows = list(reversed(_requests[-8:]))
    if not rows:
        lines.append("Пока пусто.")
    else:
        for row in rows:
            ts = datetime.fromtimestamp(int(row.get("ts") or 0), MSK).strftime("%d.%m %H:%M")
            model = model_display_name(str(row.get("model") or ""), "ru")
            lines.append(
                f"- {ts} · {model} · {_fmt_tokens(int(row.get('tokens') or 0))} ток. · {row.get('p') or '—'}"
            )
    return "\n".join(lines)


def _kb(bot_btn: Any) -> Any:
    from telebot.types import InlineKeyboardMarkup
    kb = InlineKeyboardMarkup()
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        bot_btn("Обновить", callback_data="adm:home"),
        bot_btn("Блок", callback_data="adm:block"),
        bot_btn("Разблок", callback_data="adm:unblock"),
    )
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        bot_btn("Пополнить", callback_data="adm:topup"),
        bot_btn("Рассылка", callback_data="adm:cast"),
    )
    kb.row(bot_btn("Закрыть", style="danger", callback_data="adm:close"))  # pyright: ignore[reportUnknownMemberType]
    return kb


async def open_tg(bot: Any, chat_id: int, user_id: int, origin_id: int | None = None) -> None:
    from src.rich import send_formatted_returning_id
    from src.ui import btn
    from src.util import bind_ui_flow
    mid = await send_formatted_returning_id(chat_id, home_text(), reply_markup=_kb(btn))
    bind_ui_flow(mid, chat_id, user_id, origin_id=origin_id)


async def _edit_tg(bot: Any, chat_id: int, message_id: int, text: str, kb: Any) -> None:
    from src.rich import edit_rich_message
    from src.util import markdown_like_to_telegram_html
    if await edit_rich_message(chat_id, message_id, text, reply_markup=kb):
        return
    try:
        await bot.edit_message_text(
            markdown_like_to_telegram_html(text), chat_id, message_id,
            parse_mode="HTML", reply_markup=kb,
        )
    except Exception as e:
        logger.debug(f"admin edit: {e}")


def _parse_target(text: str) -> tuple[str, int, float | None] | None:
    parts = text.replace(",", ".").split()
    if not parts:
        return None
    platform = "tg"
    if parts[0].lower() in ("tg", "ds", "telegram", "discord"):
        platform = "ds" if parts[0].lower() in ("ds", "discord") else "tg"
        parts = parts[1:]
    if not parts or not parts[0].lstrip("-").isdigit():
        return None
    user_id = int(parts[0])
    amount = float(parts[1]) if len(parts) > 1 else None
    return platform, user_id, amount


async def _wipe(bot: Any, chat_id: int, *ids: int | None) -> None:
    for mid in ids:
        if not mid:
            continue
        try:
            await bot.delete_message(chat_id, mid)
        except Exception:
            pass


async def consume_tg_message(message: Any) -> bool:
    user = getattr(message, "from_user", None)
    if user is None or not is_admin_tg(user.id):
        return False
    state = _wait.get(user.id)
    if not state:
        return False
    text = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()
    if text.lower() in CANCEL_WORDS:
        ask_id = state.get("ask_id")
        _wait.pop(user.id, None)
        await _wipe(message.bot if hasattr(message, "bot") else None, message.chat.id, ask_id, message.message_id)
        # message.bot may be missing; caller passes via telebot global in handler.
        return True
    return False


async def take_admin_input(bot: Any, message: Any) -> bool:
    """Съедает ввод админа в мастере. True — сообщение обработано и дальше его слать нельзя."""
    user = getattr(message, "from_user", None)
    if user is None or not is_admin_tg(user.id):
        return False
    state = _wait.get(user.id)
    if not state:
        return False
    text = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()
    chat_id = message.chat.id
    if text.lower() in CANCEL_WORDS:
        _wait.pop(user.id, None)
        ask_id = state.get("ask_id")
        if ask_id:
            from src.telegram import dismiss_ui_flow
            await dismiss_ui_flow(chat_id, user.id, int(ask_id))
        await _wipe(bot, chat_id, message.message_id)
        return True
    step = state.get("step")
    if step in ("block", "unblock", "topup"):
        parsed = _parse_target(text)
        ask_id = state.get("ask_id")
        if not parsed or (step == "topup" and parsed[2] is None):
            await _wipe(bot, chat_id, message.message_id)
            return True
        platform, target, amount = parsed
        _wait.pop(user.id, None)
        if step == "block":
            _blocked.add(f"{platform}:{target}")
            _save(BLOCK_FILE, sorted(_blocked))
            result = f"Доступ закрыт: {platform} `{target}`."
        elif step == "unblock":
            _blocked.discard(f"{platform}:{target}")
            _save(BLOCK_FILE, sorted(_blocked))
            result = f"Доступ открыт: {platform} `{target}`."
        else:
            add_balance(platform, target, float(amount or 0), note="admin")
            result = f"Баланс пополнен: {platform} `{target}` на {float(amount or 0):.2f} ₽."
        await _wipe(bot, chat_id, message.message_id)
        if ask_id:
            await _edit_tg(bot, chat_id, int(ask_id), f"# 🛠 Админ-панель\n\n---\n\n{result}", _kb(__import__('src.ui', fromlist=['btn']).btn))
        return True
    if step == "cast_msg":
        gid = getattr(message, "media_group_id", None)
        if gid:
            key = f"{user.id}:{gid}"
            bucket = _albums.setdefault(key, [])
            bucket.append(message.message_id)
            if len(bucket) > 1:
                return True
            await asyncio.sleep(1.3)
            ids = list(_albums.pop(key, []))
        else:
            ids = [message.message_id]
        state["step"] = "cast_opts"
        state["source_chat"] = chat_id
        state["message_ids"] = ids
        state["pin"] = False
        state["delay"] = 0
        state["delete_after"] = 0
        from src.ui import btn
        ask_id = state.get("ask_id")
        if ask_id:
            await _edit_tg(bot, chat_id, int(ask_id), _cast_text(state), _cast_kb(btn))
        return True
    return False


def _cast_text(state: dict[str, Any]) -> str:
    delay = int(state.get("delay") or 0)
    delete_after = int(state.get("delete_after") or 0)
    delay_label = "нет" if not delay else (f"{delay // 60} мин" if delay >= 60 else f"{delay} с")
    delete_label = "нет" if not delete_after else (f"{delete_after // 3600} ч" if delete_after >= 3600 else f"{delete_after // 60} мин")
    return (
        "# 🛠 Рассылка\n\n"
        "---\n\n"
        "Сообщение сохранено. Уйдёт точной копией: оформление, Rich, премиум-эмодзи и вложения.\n\n"
        f"- **Закрепить:** {'да' if state.get('pin') else 'нет'}\n"
        f"- **Задержка перед отправкой:** {delay_label}\n"
        f"- **Удалить после:** {delete_label}\n"
        f"- **Получателей Telegram:** {len(_known_ids('tg'))}"
    )


def _cast_kb(bot_btn: Any) -> Any:
    from telebot.types import InlineKeyboardMarkup
    kb = InlineKeyboardMarkup()
    kb.row(bot_btn("Закрепить", callback_data="adm:pin"))  # pyright: ignore[reportUnknownMemberType]
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        bot_btn("Сразу", callback_data="adm:delay:0"),
        bot_btn("15 с", callback_data="adm:delay:15"),
        bot_btn("1 мин", callback_data="adm:delay:60"),
        bot_btn("5 мин", callback_data="adm:delay:300"),
    )
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        bot_btn("Не удалять", callback_data="adm:del:0"),
        bot_btn("1 ч", callback_data="adm:del:3600"),
        bot_btn("6 ч", callback_data="adm:del:21600"),
        bot_btn("24 ч", callback_data="adm:del:86400"),
    )
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        bot_btn("Отправить", style="success", callback_data="adm:send"),
        bot_btn("Отмена", style="danger", callback_data="adm:abort"),
    )
    return kb


async def on_tg_callback(bot: Any, call: Any) -> None:
    from src.ui import btn
    from src import telegram as tg
    msg = call.message
    data = call.data or ""
    chat_id = msg.chat.id
    user_id = call.from_user.id
    action = data.split(":", 1)[1] if ":" in data else ""
    try:
        await bot.answer_callback_query(call.id)
    except Exception:
        pass
    if action in ("home",):
        _wait.pop(user_id, None)
        await _edit_tg(bot, chat_id, msg.message_id, home_text(), _kb(btn))
        return
    if action == "close":
        _wait.pop(user_id, None)
        await tg.dismiss_ui_flow(chat_id, user_id, msg.message_id)
        return
    if action in ("block", "unblock", "topup"):
        prompts = {
            "block": "Пришли ID. Формат: `tg 123456` или `ds 123456`.\n\nОтмена — /cancel.",
            "unblock": "Пришли ID, которому открыть доступ. Формат: `tg 123456` или `ds 123456`.\n\nОтмена — /cancel.",
            "topup": "Пришли ID и сумму. Формат: `tg 123456 500` или `ds 123456 80`.\n\nОтмена — /cancel.",
        }
        _wait[user_id] = {"step": action, "ask_id": msg.message_id}
        await _edit_tg(bot, chat_id, msg.message_id, f"# 🛠 Админ-панель\n\n---\n\n{prompts[action]}", _kb(btn))
        return
    if action == "cast":
        _wait[user_id] = {"step": "cast_msg", "ask_id": msg.message_id}
        await _edit_tg(
            bot, chat_id, msg.message_id,
            "# 🛠 Рассылка\n\n---\n\nПришли сообщение, которое нужно разослать. "
            "Подойдёт текст, Rich, премиум-эмодзи, альбом и любое вложение.\n\nОтмена — /cancel.",
            _kb(btn),
        )
        return
    state = _wait.get(user_id)
    if not state or state.get("step") != "cast_opts":
        return
    if action == "pin":
        state["pin"] = not bool(state.get("pin"))
    elif action.startswith("delay:"):
        state["delay"] = int(action.split(":", 1)[1] or 0)
    elif action.startswith("del:"):
        state["delete_after"] = int(action.split(":", 1)[1] or 0)
    elif action == "abort":
        _wait.pop(user_id, None)
        await tg.dismiss_ui_flow(chat_id, user_id, msg.message_id)
        return
    elif action == "send":
        _wait.pop(user_id, None)
        await _edit_tg(bot, chat_id, msg.message_id, "# 🛠 Рассылка\n\n---\n\nОтправляю.", None)
        sent, failed = await _broadcast_tg(bot, state)
        await _edit_tg(
            bot, chat_id, msg.message_id,
            f"# 🛠 Рассылка\n\n---\n\nГотово.\n\n- **Доставлено:** {sent}\n- **Не доставлено:** {failed}",
            _kb(btn),
        )
        return
    await _edit_tg(bot, chat_id, msg.message_id, _cast_text(state), _cast_kb(btn))


async def _delete_later_tg(bot: Any, chat_id: int, message_ids: list[int], delay: int) -> None:
    await asyncio.sleep(delay)
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id, mid)
        except Exception:
            pass


async def _broadcast_tg(bot: Any, state: dict[str, Any]) -> tuple[int, int]:
    delay = int(state.get("delay") or 0)
    if delay:
        await asyncio.sleep(delay)
    sent = 0
    failed = 0
    source_chat = int(state.get("source_chat") or 0)
    message_ids = [int(x) for x in state.get("message_ids") or []]
    for uid in sorted(_known_ids("tg")):
        if uid in ADMIN_TG_IDS or is_blocked("tg", uid):
            continue
        copied: list[int] = []
        try:
            for mid in message_ids:
                result = await bot.copy_message(uid, source_chat, mid)
                new_id = getattr(result, "message_id", None)
                if new_id:
                    copied.append(int(new_id))
            if state.get("pin") and copied:
                try:
                    await bot.pin_chat_message(uid, copied[0], disable_notification=True)
                except Exception:
                    pass
            if state.get("delete_after") and copied:
                asyncio.create_task(_delete_later_tg(bot, uid, copied, int(state["delete_after"])))
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    return sent, failed


async def open_ds(message: Any) -> None:
    import discord
    embed = discord.Embed(title="Админ-панель", description=_ds_home(), color=0xA75FFF)
    await message.channel.send(embed=embed, view=DsAdminView(message.author.id))


def _ds_home() -> str:
    text = home_text()
    return re.sub(r"^# .+\n\n---\n\n", "", text)


class DsAdminView:
    """Собирается лениво, чтобы не тянуть discord при импорте тестов без стаба."""

    def __new__(cls, user_id: int) -> Any:
        import discord
        view = discord.ui.View(timeout=600)
        view.user_id = user_id  # type: ignore[attr-defined]

        async def _check(interaction: Any) -> bool:
            if interaction.user.id != user_id or not is_admin_ds(interaction.user.id):
                return False
            return True

        view.interaction_check = _check  # type: ignore[method-assign]

        async def _home(interaction: Any) -> None:
            _wait.pop(interaction.user.id, None)
            await interaction.response.edit_message(embed=discord.Embed(
                title="Админ-панель", description=_ds_home(), color=0xA75FFF,
            ), view=DsAdminView(user_id))

        async def _ask(interaction: Any, step: str, text: str) -> None:
            _wait[interaction.user.id] = {"step": step, "platform": "ds"}
            await interaction.response.send_message(text, ephemeral=True)

        async def _block(interaction: Any) -> None:
            await _ask(interaction, "block", "Пришли `tg 123456` или `ds 123456`. Отмена — /cancel.")

        async def _unblock(interaction: Any) -> None:
            await _ask(interaction, "unblock", "Пришли ID для разблокировки. Отмена — /cancel.")

        async def _topup(interaction: Any) -> None:
            await _ask(interaction, "topup", "Пришли `tg 123456 500` или `ds 123456 80`. Отмена — /cancel.")

        async def _cast(interaction: Any) -> None:
            await _ask(
                interaction, "cast_msg",
                "Пришли сообщение для рассылки. Оформление, вложения и эмодзи сохранятся. Отмена — /cancel.",
            )

        home = discord.ui.Button(label="Обновить", style=discord.ButtonStyle.secondary, row=0)
        home.callback = _home
        view.add_item(home)
        block = discord.ui.Button(label="Блок", style=discord.ButtonStyle.secondary, row=0)
        block.callback = _block
        view.add_item(block)
        unblock = discord.ui.Button(label="Разблок", style=discord.ButtonStyle.secondary, row=0)
        unblock.callback = _unblock
        view.add_item(unblock)
        topup = discord.ui.Button(label="Пополнить", style=discord.ButtonStyle.secondary, row=1)
        topup.callback = _topup
        view.add_item(topup)
        cast = discord.ui.Button(label="Рассылка", style=discord.ButtonStyle.secondary, row=1)
        cast.callback = _cast
        view.add_item(cast)
        return view


async def take_admin_ds(message: Any) -> bool:
    if not is_admin_ds(message.author.id):
        return False
    state = _wait.get(message.author.id)
    if not state or state.get("platform") != "ds":
        return False
    text = (message.content or "").strip()
    if text.lower() in CANCEL_WORDS:
        _wait.pop(message.author.id, None)
        try:
            await message.delete()
        except Exception:
            pass
        return True
    step = state.get("step")
    if step in ("block", "unblock", "topup"):
        parsed = _parse_target(text)
        if not parsed or (step == "topup" and parsed[2] is None):
            try:
                await message.delete()
            except Exception:
                pass
            return True
        platform, target, amount = parsed
        _wait.pop(message.author.id, None)
        if step == "block":
            _blocked.add(f"{platform}:{target}")
            _save(BLOCK_FILE, sorted(_blocked))
            result = f"Доступ закрыт: {platform} `{target}`."
        elif step == "unblock":
            _blocked.discard(f"{platform}:{target}")
            _save(BLOCK_FILE, sorted(_blocked))
            result = f"Доступ открыт: {platform} `{target}`."
        else:
            add_balance(platform, target, float(amount or 0), note="admin")
            result = f"Баланс пополнен: {platform} `{target}` на {float(amount or 0):.2f} ₽."
        try:
            await message.delete()
        except Exception:
            pass
        await message.channel.send(result)
        return True
    if step == "cast_msg":
        gid = getattr(message, "message_reference", None)
        key = f"ds:{message.author.id}"
        bucket = _ds_albums.setdefault(key, [])
        bucket.append(message)
        if len(bucket) > 1:
            return True
        await asyncio.sleep(1.2)
        messages = list(_ds_albums.pop(key, []))
        state["step"] = "cast_opts"
        state["ds_messages"] = messages
        state["pin"] = False
        state["delay"] = 0
        state["delete_after"] = 0
        import discord
        view = discord.ui.View(timeout=600)

        async def _toggle(interaction: Any, field: str, value: int | None = None) -> None:
            cur = _wait.get(message.author.id)
            if not cur:
                return
            if field == "pin":
                cur["pin"] = not cur.get("pin")
            else:
                cur[field] = value
            await interaction.response.edit_message(content=_cast_text(cur), view=view)

        async def _pin(interaction: Any) -> None:
            await _toggle(interaction, "pin")

        pin = discord.ui.Button(label="Закрепить", row=0)
        pin.callback = _pin
        view.add_item(pin)
        for label, sec in (("Сразу", 0), ("15 с", 15), ("1 мин", 60), ("5 мин", 300)):
            button = discord.ui.Button(label=label, row=1)

            async def _delay(interaction: Any, sec: int = sec) -> None:
                await _toggle(interaction, "delay", sec)

            button.callback = _delay
            view.add_item(button)
        for label, sec in (("Не удалять", 0), ("1 ч", 3600), ("24 ч", 86400)):
            button = discord.ui.Button(label=label, row=2)

            async def _delete(interaction: Any, sec: int = sec) -> None:
                await _toggle(interaction, "delete_after", sec)

            button.callback = _delete
            view.add_item(button)

        async def _send(interaction: Any) -> None:
            cur = _wait.pop(message.author.id, None)
            await interaction.response.defer()
            if not cur:
                return
            sent, failed = await _broadcast_ds(cur)
            await interaction.followup.send(f"Готово. Доставлено: {sent}. Не доставлено: {failed}.")

        async def _abort(interaction: Any) -> None:
            _wait.pop(message.author.id, None)
            try:
                await interaction.message.delete()
            except Exception:
                await interaction.response.defer()

        go = discord.ui.Button(label="Отправить", style=discord.ButtonStyle.success, row=3)
        go.callback = _send
        view.add_item(go)
        stop = discord.ui.Button(label="Отмена", style=discord.ButtonStyle.danger, row=3)
        stop.callback = _abort
        view.add_item(stop)
        await message.channel.send(_cast_text(state), view=view)
        return True
    return False


async def _broadcast_ds(state: dict[str, Any]) -> tuple[int, int]:
    from src.discord_cmds import ds_bot
    delay = int(state.get("delay") or 0)
    if delay:
        await asyncio.sleep(delay)
    sent = 0
    failed = 0
    sources = list(state.get("ds_messages") or [])
    for uid in sorted(_known_ids("ds")):
        if uid in ADMIN_DS_IDS or is_blocked("ds", uid) or ds_bot is None:
            continue
        try:
            user = ds_bot.get_user(uid) or await ds_bot.fetch_user(uid)
            copied = []
            for src in sources:
                files = [await att.to_file() for att in getattr(src, "attachments", [])]
                kwargs: dict[str, Any] = {"content": src.content or None, "embeds": list(src.embeds)}
                if files:
                    kwargs["files"] = files
                stickers = list(getattr(src, "stickers", []) or [])
                if stickers:
                    kwargs["stickers"] = stickers
                try:
                    copied.append(await user.send(**kwargs))
                except Exception:
                    kwargs.pop("stickers", None)
                    copied.append(await user.send(**kwargs))
            if state.get("pin"):
                for item in copied:
                    try:
                        await item.pin()
                    except Exception:
                        pass
            if state.get("delete_after"):
                asyncio.create_task(_delete_later_ds(copied, int(state["delete_after"])))
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    return sent, failed


async def _delete_later_ds(messages: list[Any], delay: int) -> None:
    await asyncio.sleep(delay)
    for msg in messages:
        try:
            await msg.delete()
        except Exception:
            pass
