# Kulsh GPT | v2.49.0
# by (main author): starfall-apk
# coauthor & bot hosting: pomidorka1515

"""Telegram balance / profile / support screens (rich text, Kulsh style)."""

from __future__ import annotations

import html
import re
from typing import Any

from telebot.types import InlineKeyboardMarkup

from src.billing import (
    DONATIONALERTS_PAGE,
    MIN_TOPUP_RUB,
    PRIVACY_URL,
    SUPPORT_ADMIN_TG,
    TERMS_URL,
    append_ticket_message,
    create_ticket,
    get_balance,
    get_ticket,
    get_topup_count,
    get_total_topup,
    map_admin_message,
    poll_donations_once,
    topup_code,
)
from src.rich import edit_rich_message, send_formatted, send_formatted_returning_id
from src.ui import btn
from src.util import DONATE_URL, bind_ui_flow, config_children_msgs, logger, markdown_like_to_telegram_html

SUPPORT_WAITING: dict[int, dict[str, int]] = {}

TXT = {
    "balance_title": ("💳 Баланс", "💳 Balance"),
    "profile_title": ("👤 Профиль", "👤 Profile"),
    "on_account": ("На счёте", "On account"),
    "topped": ("Пополнено", "Topped up"),
    "topup_section": ("Пополнение", "Top up"),
    "tag": ("Твой тег для пополнения", "Your top-up tag"),
    "min": ("Минимальная сумма", "Minimum amount"),
    "pay": ("Ссылка на оплату", "Payment link"),
    "pay_action": ("Оплатить", "Pay"),
    "code_hint": (
        "Вставь код в поле «Сообщение» при оплате. Без него платёж не привяжется к аккаунту.",
        "Put the code into the donation message. Without it the payment will not be linked to the account.",
    ),
    "auto_note": (
        "Зачисление обычно проходит само. Если платёж не пришёл — нажми «Проверить платёж».",
        "It is usually credited on its own. If it does not arrive, press “Check payment”.",
    ),
    "tg_id": ("Telegram ID", "Telegram ID"),
    "topups": ("Пополнений", "Top-ups"),
    "profile_note": ("Пополнение открывается командой /balance.", "Top-up opens with /balance."),
    "check": ("🔄 Проверить платёж", "🔄 Check payment"),
    "support": ("💬 Поддержка", "💬 Support"),
    "close": ("❌ Закрыть", "❌ Close"),
    "paid": ("Зачислено: +{0:.2f} ₽", "Credited: +{0:.2f} ₽"),
    "nothing": ("Новых платежей не видно. Если донат был только что — подожди минуту и проверь ещё раз.",
                "No new payments yet. If you just donated, wait a minute and check again."),
    "dm_sent": ("🍷 Меню баланса — у тебя в личке", "🍷 The balance menu is in your DM"),
    "dm_fail": (
        "Не смог написать тебе в личку — открой чат со мной и нажми /start:\n{0}",
        "Couldn't DM you — open a chat with me and press /start:\n{0}",
    ),
    "support_ask": (
        "Опиши проблему одним сообщением — я передам её в поддержку. Напиши /cancel, чтобы отменить.",
        "Describe the issue in one message — I'll pass it to support. Send /cancel to cancel.",
    ),
    "support_cancel": ("Ок, отменил.", "Okay, cancelled."),
    "support_ok": ("Обращение №{0} принято. Ответ придёт сюда.", "Ticket #{0} accepted. The reply will arrive here."),
    "support_reply": ("💬 Ответ поддержки по обращению №{0}:\n\n{1}", "💬 Support reply to ticket #{0}:\n\n{1}"),
    "support_relayed": ("Ответ отправлен пользователю (обращение №{0}).", "Reply delivered (ticket #{0})."),
    "checking": ("Проверяю…", "Checking…"),
    "support_label": ("Поддержка", "Support"),
    "terms": ("Пользовательское соглашение", "Terms of Service"),
    "privacy": ("Политика конфиденциальности", "Privacy Policy"),
}


def t(lang: str, key: str, *args: Any) -> str:
    ru, en = TXT.get(key, ("", ""))
    s = ru if lang == "ru" else en
    try:
        return s.format(*args)
    except Exception:
        return s


def _money(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def _safe(text: str) -> str:
    """Убирает символы, которые rich-парсер воспринимает как разметку."""
    return re.sub(r'[*_`\[\]]', '', (text or "").strip())[:32]


def _legal(lang: str) -> str:
    return f"[{t(lang, 'terms')}]({TERMS_URL}) · [{t(lang, 'privacy')}]({PRIVACY_URL})"


def balance_text(lang: str, user_id: int, nick: str) -> str:
    del nick
    bal = _money(get_balance("tg", user_id))
    total = _money(get_total_topup("tg", user_id))
    code = topup_code("tg", user_id)
    pay_url = DONATIONALERTS_PAGE or DONATE_URL
    return (
        f"# {t(lang, 'balance_title')}\n\n"
        f"---\n\n"
        f"|*{t(lang, 'on_account')}*|*{t(lang, 'topped')}*|\n"
        f"|{bal} ₽|{total} ₽|\n\n"
        f"---\n\n"
        f"**{t(lang, 'topup_section')}**\n\n"
        f"- **{t(lang, 'tag')}:** `{code}`\n"
        f"- **{t(lang, 'min')}:** {MIN_TOPUP_RUB:.0f} ₽\n"
        f"- **{t(lang, 'pay')}:** [{t(lang, 'pay_action')}]({pay_url})\n\n"
        f"> {t(lang, 'code_hint')}\n\n"
        f"{t(lang, 'auto_note')}\n\n"
        f"---\n\n"
        f"{_legal(lang)}"
    )


def profile_text(lang: str, user_id: int, nick: str) -> str:
    del nick
    bal = _money(get_balance("tg", user_id))
    total = _money(get_total_topup("tg", user_id))
    count = get_topup_count("tg", user_id)
    return (
        f"# {t(lang, 'profile_title')}\n\n"
        f"---\n\n"
        f"|*{t(lang, 'tg_id')}*|*{t(lang, 'on_account')}*|\n"
        f"|`{user_id}`|{bal} ₽|\n\n"
        f"- **{t(lang, 'topped')}:** {total} ₽\n"
        f"- **{t(lang, 'topups')}:** {count}\n\n"
        f"---\n\n"
        f"{t(lang, 'profile_note')}"
    )


def balance_keyboard(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        btn(t(lang, "check"), style=None, callback_data="menu:checkpay"),
        btn(t(lang, "support"), style=None, callback_data="menu:support"),
    )
    kb.row(btn(t(lang, "close"), style="danger", callback_data="menu:close"))  # pyright: ignore[reportUnknownMemberType]
    return kb


def profile_keyboard(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(btn(t(lang, "close"), style="danger", callback_data="menu:close"))  # pyright: ignore[reportUnknownMemberType]
    return kb


def screen_text(screen: str, lang: str, user_id: int, nick: str) -> str:
    if screen == "profile":
        return profile_text(lang, user_id, nick)
    return balance_text(lang, user_id, nick)


def screen_keyboard(screen: str, lang: str) -> InlineKeyboardMarkup:
    if screen == "profile":
        return profile_keyboard(lang)
    return balance_keyboard(lang)


async def edit_screen_tg(bot: Any, chat_id: int, message_id: int, screen: str,
                         lang: str, user_id: int, nick: str) -> bool:
    text = screen_text(screen, lang, user_id, nick)
    kb = screen_keyboard(screen, lang)
    if await edit_rich_message(chat_id, message_id, text, reply_markup=kb):
        return True
    try:
        await bot.edit_message_text(
            markdown_like_to_telegram_html(text), chat_id=chat_id, message_id=message_id,
            parse_mode="HTML", reply_markup=kb,
        )
        return True
    except Exception as e:
        if "message is not modified" in str(e):
            return True
        logger.debug(f"balance edit: {e}")
        return False


async def _dm_screen(bot: Any, chat_id: int, user_id: int, lang: str, nick: str,
                     screen: str, reply_to: int | None) -> None:
    text = screen_text(screen, lang, user_id, nick)
    kb = screen_keyboard(screen, lang)
    extra: list[tuple[int, int]] = []
    if reply_to:
        extra.append((chat_id, reply_to))
    try:
        mid = await send_formatted_returning_id(user_id, text, reply_markup=kb)
        if not mid:
            raise RuntimeError("dm closed")
    except Exception as e:
        logger.warning(f"balance dm: {e}")
        username = getattr(getattr(bot, "user", None), "username", "") or ""
        link = f"https://t.me/{username}?start={screen}" if username else "—"
        await send_formatted(chat_id, t(lang, "dm_fail", link), reply_to=reply_to)
        return
    note_id = None
    try:
        note = await bot.send_message(chat_id, t(lang, "dm_sent"), reply_to_message_id=reply_to)
        note_id = getattr(note, "message_id", None)
    except Exception:
        note_id = None
    if note_id:
        extra.append((chat_id, note_id))
    bind_ui_flow(mid, user_id, user_id, origin_id=None, extra=extra)


async def send_balance_menu_tg(bot: Any, chat_id: int, user_id: int, lang: str,
                               nick: str, reply_to: int | None = None, origin_id: int | None = None) -> None:
    await send_screen_tg(bot, chat_id, user_id, lang, nick, screen="balance",
                         reply_to=reply_to, origin_id=origin_id or reply_to)


async def send_profile_tg(bot: Any, chat_id: int, user_id: int, lang: str,
                          nick: str, reply_to: int | None = None, origin_id: int | None = None) -> None:
    await send_screen_tg(bot, chat_id, user_id, lang, nick, screen="profile",
                         reply_to=reply_to, origin_id=origin_id or reply_to)


async def send_screen_tg(bot: Any, chat_id: int, user_id: int, lang: str, nick: str,
                         screen: str = "balance", reply_to: int | None = None,
                         origin_id: int | None = None) -> None:
    if chat_id != user_id:
        await _dm_screen(bot, chat_id, user_id, lang, nick, screen, reply_to)
        return
    mid = await send_formatted_returning_id(
        chat_id, screen_text(screen, lang, user_id, nick),
        reply_to=reply_to, reply_markup=screen_keyboard(screen, lang),
    )
    bind_ui_flow(mid, chat_id, user_id, origin_id=origin_id or reply_to)


async def check_payment_tg(bot: Any, chat_id: int, user_id: int, lang: str) -> None:
    credited = await poll_donations_once()
    mine = [c for c in credited if c[0] == "tg" and c[1] == user_id]
    text = t(lang, "paid", sum(c[2] for c in mine)) if mine else t(lang, "nothing")
    if chat_id != user_id:
        try:
            await bot.send_message(user_id, text)
            return
        except Exception:
            text = t(lang, "dm_fail", "—")
    try:
        await bot.send_message(chat_id, text)
    except Exception as e:
        logger.warning(f"check payment send: {e}")


async def start_support_tg(bot: Any, chat_id: int, user_id: int, lang: str) -> None:
    ask_id = 0
    try:
        sent = await bot.send_message(chat_id, t(lang, "support_ask"))
        ask_id = int(getattr(sent, "message_id", 0) or 0)
    except Exception as e:
        logger.warning(f"support ask: {e}")
    SUPPORT_WAITING[user_id] = {"chat_id": chat_id, "ask_id": ask_id}
    if ask_id:
        config_children_msgs.setdefault((chat_id, user_id), []).append(ask_id)


async def submit_support_tg(bot: Any, user_id: int, chat_id: int, text: str, lang: str) -> None:
    SUPPORT_WAITING.pop(user_id, None)
    tid = create_ticket("tg", user_id, chat_id, text)
    await bot.send_message(chat_id, t(lang, "support_ok", tid))
    if not SUPPORT_ADMIN_TG:
        return
    admin_text = (
        f"🎫 Обращение №{tid}\n"
        f"Платформа: Telegram\n"
        f"Пользователь: {user_id}\n\n"
        f"{text}\n\n"
        f"↩️ Ответь на это сообщение, чтобы передать ответ пользователю."
    )
    try:
        sent = await bot.send_message(SUPPORT_ADMIN_TG, admin_text)
        map_admin_message("tg", sent.message_id, tid)
    except Exception as e:
        logger.warning(f"support admin send: {e}")


async def relay_support_reply_tg(bot: Any, tid: int, text: str) -> None:
    ticket = get_ticket(tid)
    if not ticket:
        return
    append_ticket_message(tid, "support", text)
    platform = str(ticket.get("platform") or "tg")
    user_id = int(ticket.get("user_id") or 0)
    if platform != "tg" or not user_id:
        return
    try:
        pretty = (
            f"💬 **Ответ поддержки**\n\n"
            f"**Обращение №{tid}**\n\n{html.escape(text)}"
        )
        await send_formatted(user_id, pretty)
        if SUPPORT_ADMIN_TG:
            await bot.send_message(SUPPORT_ADMIN_TG, t("ru", "support_relayed", tid))
    except Exception as e:
        logger.warning(f"support relay: {e}")
