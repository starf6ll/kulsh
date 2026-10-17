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
from src import cloud, promo
from src.rich import edit_rich_message, send_formatted, send_formatted_returning_id
from src.ui import btn
from src.util import DONATE_URL, bind_ui_flow, config_children_msgs, logger, markdown_like_to_telegram_html

SUPPORT_WAITING: dict[int, dict[str, int]] = {}
# Ожидание ввода для аккаунта: промокод, имя API-ключа, номер ключа.
ACCOUNT_WAITING: dict[int, dict[str, Any]] = {}
# Невидимый абзац: rich-рендер не схлопывает его, поэтому он даёт пустую строку-отступ.
_GAP = "\u2060"

PROVIDER_NAMES = {
    "tg": ("Telegram", "Telegram"),
    "telegram": ("Telegram", "Telegram"),
    "ds": ("Discord", "Discord"),
    "google": ("Google", "Google"),
    "github": ("GitHub", "GitHub"),
}

TXT = {
    "balance_title": ("💳 Баланс", "💳 Balance"),
    "profile_title": ("👤 Профиль", "👤 Profile"),
    "on_account": ("На счёте", "On account"),
    "topped": ("Пополнено", "Topped up"),
    "topup_section": ("Пополнение", "Top up"),
    "tag": ("Твой тег для пополнения", "Your top-up tag"),
    "min": ("Минимальная сумма", "Minimum amount"),
    "pay": ("Ссылка на оплату", "Payment link"),
    "code_hint": (
        "Вставь тег в поле «Сообщение» при оплате. Без него платёж не привяжется к аккаунту.",
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
    "back": ("⬅️ Назад", "⬅️ Back"),
    "link_btn": ("🔗 Привязать аккаунт", "🔗 Link account"),
    "api_btn": ("🔑 API-ключи", "🔑 API keys"),
    "promo_btn": ("🎁 Промокод", "🎁 Promo code"),
    "linked": ("Привязано", "Linked"),
    "tokens_today": ("Токенов сегодня", "Tokens today"),
    "api_count": ("API-ключей", "API keys"),
    "bonus_line": ("Бонус к пополнению", "Top-up bonus"),
    "link_title": ("🔗 Привязка аккаунта", "🔗 Link account"),
    "link_code": ("Код для сайта", "Code for the site"),
    "link_ttl": ("Действует", "Valid for"),
    "link_ttl_value": ("15 минут", "15 minutes"),
    "link_site": ("Сайт", "Website"),
    "link_hint": (
        "Войди на сайте через Google или GitHub, открой меню аккаунта, выбери «Привязать» и введи этот код. "
        "Баланс, usage и API-ключи станут общими. Если у аккаунта уже есть баланс — суммы сложатся, сайт предупредит об этом.",
        "Sign in on the site with Google or GitHub, open the account menu, choose “Link” and enter this code. "
        "Balance, usage and API keys become shared. If the account already has a balance, the amounts are summed and the site warns you first.",
    ),
    "link_off": (
        "Привязка временно недоступна: общее хранилище не настроено. Администратору — переменные `KV_REST_API_URL` и `KV_REST_API_TOKEN`.",
        "Linking is temporarily unavailable: shared storage is not configured. For the admin — `KV_REST_API_URL` and `KV_REST_API_TOKEN`.",
    ),
    "link_fail": (
        "Не удалось сохранить код. Проверь связь с Redis и попробуй ещё раз.",
        "Could not save the code. Check the Redis connection and try again.",
    ),
    "api_title": ("🔑 API-ключи", "🔑 API keys"),
    "api_empty": ("Ключей пока нет.", "No keys yet."),
    "api_new": ("➕ Создать ключ", "➕ Create key"),
    "api_revoke": ("🗑 Отозвать", "🗑 Revoke"),
    "api_name_ask": (
        "Пришли название нового ключа одним сообщением. Напиши /cancel, чтобы отменить.",
        "Send a name for the new key in one message. Send /cancel to cancel.",
    ),
    "api_revoke_ask": (
        "Пришли номер ключа, который нужно отозвать. Напиши /cancel, чтобы отменить.",
        "Send the number of the key to revoke. Send /cancel to cancel.",
    ),
    "api_created": (
        "Ключ создан. Скопируй его сейчас — больше он не покажется:\n\n`{0}`",
        "Key created. Copy it now — it will not be shown again:\n\n`{0}`",
    ),
    "api_revoked": ("Ключ отозван.", "Key revoked."),
    "api_limit": ("Лимит — 10 ключей. Отзови один из старых.", "Limit is 10 keys. Revoke an old one."),
    "api_bad": ("Не понял. Пришли номер ключа из списка.", "Didn't get it. Send a key number from the list."),
    "api_hint": (
        "Ключи работают с публичным API: `https://kulsh.vercel.app/api/v1`. Секрет показывается один раз.",
        "Keys work with the public API: `https://kulsh.vercel.app/api/v1`. The secret is shown once.",
    ),
    "promo_title": ("🎁 Промокод", "🎁 Promo code"),
    "promo_ask": (
        "Пришли промокод одним сообщением. Напиши /cancel, чтобы отменить.",
        "Send the promo code in one message. Send /cancel to cancel.",
    ),
    "promo_ok": ("Промокод активирован. {0}", "Promo code activated. {0}"),
    "promo_fail": ("Не вышло: {0}", "Could not activate: {0}"),
    "promo_placeholder": ("Активация промокода", "Promo activation"),
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
    bonus = cloud.get_bonus(cloud.resolve("tg", user_id)) if cloud.enabled() else 0
    bonus_line = f"- **{t(lang, 'bonus_line')}:** +{bonus}%\n" if bonus else ""
    return (
        f"# {t(lang, 'balance_title')}\n\n"
        f"---\n\n"
        f"|*{t(lang, 'on_account')}*|*{t(lang, 'topped')}*|\n"
        f"|{bal} ₽|{total} ₽|\n\n"
        f"---\n\n"
        f"**{t(lang, 'topup_section')}**\n\n"
        f"- **{t(lang, 'tag')}:** `{code}`\n"
        f"- **{t(lang, 'min')}:** {MIN_TOPUP_RUB:.0f} ₽\n"
        f"{bonus_line}"
        f"- **[{t(lang, 'pay')}]({pay_url})**\n\n"
        f"{_GAP}\n\n"
        f"> {t(lang, 'code_hint')}\n\n"
        f"{_GAP}\n\n"
        f"{t(lang, 'auto_note')}\n\n"
        f"---\n\n"
        f"{_legal(lang)}"
    )


def _linked_services(lang: str, user_id: int) -> str:
    if not cloud.enabled():
        return "Telegram" if lang == "ru" else "Telegram"
    acct = cloud.resolve("tg", user_id)
    names: list[str] = []
    for ident in cloud.account_ids(acct):
        provider = ident.split(":", 1)[0]
        label = PROVIDER_NAMES.get(provider, (provider, provider))[0 if lang == "ru" else 1]
        if label not in names:
            names.append(label)
    return ", ".join(names) or ("—", "—")[0 if lang == "ru" else 1]


def profile_text(lang: str, user_id: int, nick: str) -> str:
    del nick
    bal = _money(get_balance("tg", user_id))
    total = _money(get_total_topup("tg", user_id))
    count = get_topup_count("tg", user_id)
    linked = _linked_services(lang, user_id)
    usage_line = ""
    keys_line = ""
    if cloud.enabled():
        acct = cloud.resolve("tg", user_id)
        used = int(cloud.usage(acct).get("used") or 0)
        usage_line = f"- **{t(lang, 'tokens_today')}:** {_tokens(used)} / {_tokens(100000)}\n"
        keys_line = f"- **{t(lang, 'api_count')}:** {len(cloud.list_api_keys(acct))}\n"
    return (
        f"# {t(lang, 'profile_title')}\n\n"
        f"---\n\n"
        f"|*{t(lang, 'tg_id')}*|*{t(lang, 'on_account')}*|\n"
        f"|`{user_id}`|{bal} ₽|\n\n"
        f"{_GAP}\n\n"
        f"- **{t(lang, 'topped')}:** {total} ₽\n"
        f"- **{t(lang, 'topups')}:** {count}\n"
        f"- **{t(lang, 'linked')}:** {linked}\n"
        f"{usage_line}"
        f"{keys_line}\n"
        f"---\n\n"
        f"{t(lang, 'profile_note')}"
    )


def _tokens(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")


def link_text(lang: str, code: str, nick: str = "", error: str = "") -> str:
    site = "https://kulsh.vercel.app/chat"
    if error:
        return (
            f"# {t(lang, 'link_title')}\n\n"
            f"---\n\n"
            f"{error}\n\n"
            f"---\n\n"
            f"{_legal(lang)}"
        )
    return (
        f"# {t(lang, 'link_title')}\n\n"
        f"---\n\n"
        f"- **{t(lang, 'link_code')}:** `{code}`\n"
        f"- **{t(lang, 'link_ttl')}:** {t(lang, 'link_ttl_value')}\n"
        f"- **{t(lang, 'link_site')}:** [kulsh.vercel.app]({site})\n\n"
        f"{_GAP}\n\n"
        f"> {t(lang, 'link_hint')}\n\n"
        f"{_GAP}\n\n"
        f"---\n\n"
        f"{_legal(lang)}"
    )


def api_text(lang: str, user_id: int) -> str:
    lines = [f"# {t(lang, 'api_title')}", "", "---", ""]
    if not cloud.enabled():
        lines.append(t(lang, "api_hint"))
        return "\n".join(lines)
    acct = cloud.resolve("tg", user_id)
    keys = cloud.list_api_keys(acct)
    if not keys:
        lines.append(t(lang, "api_empty"))
    else:
        for i, key in enumerate(keys, 1):
            name = _safe(str(key.get("name") or "Ключ"))
            prefix = str(key.get("prefix") or "")
            lines.append(f"- **{i}. {name}** — `{prefix}`")
    lines += ["", "---", "", t(lang, "api_hint")]
    return "\n".join(lines)


def balance_keyboard(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        btn(t(lang, "check"), style=None, callback_data="menu:checkpay"),
        btn(t(lang, "support"), style=None, callback_data="menu:support"),
    )
    kb.row(btn(t(lang, "promo_btn"), style=None, callback_data="menu:promo"))  # pyright: ignore[reportUnknownMemberType]
    kb.row(btn(t(lang, "close"), style="danger", callback_data="menu:close"))  # pyright: ignore[reportUnknownMemberType]
    return kb


def profile_keyboard(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        btn(t(lang, "link_btn"), style=None, callback_data="menu:link"),
        btn(t(lang, "api_btn"), style=None, callback_data="menu:api"),
    )
    kb.row(btn(t(lang, "promo_btn"), style=None, callback_data="menu:promo"))  # pyright: ignore[reportUnknownMemberType]
    kb.row(btn(t(lang, "close"), style="danger", callback_data="menu:close"))  # pyright: ignore[reportUnknownMemberType]
    return kb


def link_keyboard(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(btn(t(lang, "back"), style=None, callback_data="menu:profile"))  # pyright: ignore[reportUnknownMemberType]
    kb.row(btn(t(lang, "close"), style="danger", callback_data="menu:close"))  # pyright: ignore[reportUnknownMemberType]
    return kb


def api_keyboard(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(  # pyright: ignore[reportUnknownMemberType]
        btn(t(lang, "api_new"), style=None, callback_data="menu:api_new"),
        btn(t(lang, "api_revoke"), style=None, callback_data="menu:api_revoke"),
    )
    kb.row(btn(t(lang, "back"), style=None, callback_data="menu:profile"))  # pyright: ignore[reportUnknownMemberType]
    kb.row(btn(t(lang, "close"), style="danger", callback_data="menu:close"))  # pyright: ignore[reportUnknownMemberType]
    return kb


def screen_text(screen: str, lang: str, user_id: int, nick: str) -> str:
    if screen == "profile":
        return profile_text(lang, user_id, nick)
    if screen == "link":
        if not cloud.enabled():
            return link_text(lang, "", nick, error=t(lang, "link_off"))
        code = cloud.create_link_code("tg", user_id, name=nick)
        if not code or not cloud.read_link_code(code):
            return link_text(lang, "", nick, error=t(lang, "link_fail"))
        return link_text(lang, code, nick)
    if screen == "api":
        return api_text(lang, user_id)
    return balance_text(lang, user_id, nick)


def screen_keyboard(screen: str, lang: str) -> InlineKeyboardMarkup:
    if screen == "profile":
        return profile_keyboard(lang)
    if screen == "link":
        return link_keyboard(lang)
    if screen == "api":
        return api_keyboard(lang)
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


# ============================================================
# ACCOUNT: LINK / API KEYS / PROMO
# ============================================================
_CANCEL = {"/cancel", "отмена", "cancel", "/отмена", "отменить"}


async def _ask_input(bot: Any, chat_id: int, user_id: int, text: str, kind: str) -> None:
    try:
        sent = await bot.send_message(chat_id, text)
    except Exception as e:
        logger.warning(f"account ask: {e}")
        return
    ask_id = int(getattr(sent, "message_id", 0) or 0)
    ACCOUNT_WAITING[user_id] = {"kind": kind, "chat_id": chat_id, "ask_id": ask_id}
    if ask_id:
        config_children_msgs.setdefault((chat_id, user_id), []).append(ask_id)


async def start_promo_tg(bot: Any, chat_id: int, user_id: int, lang: str) -> None:
    await _ask_input(bot, chat_id, user_id, t(lang, "promo_ask"), "promo")


async def start_api_new_tg(bot: Any, chat_id: int, user_id: int, lang: str) -> None:
    await _ask_input(bot, chat_id, user_id, t(lang, "api_name_ask"), "api_name")


async def start_api_revoke_tg(bot: Any, chat_id: int, user_id: int, lang: str) -> None:
    await _ask_input(bot, chat_id, user_id, t(lang, "api_revoke_ask"), "api_revoke")


async def _edit_plain(bot: Any, chat_id: int, message_id: int, text: str) -> None:
    if await edit_rich_message(chat_id, message_id, text):
        return
    try:
        await bot.edit_message_text(
            markdown_like_to_telegram_html(text), chat_id=chat_id, message_id=message_id,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.debug(f"account edit: {e}")


async def _wipe(bot: Any, chat_id: int, *ids: int | None) -> None:
    for mid in ids:
        if not mid:
            continue
        try:
            await bot.delete_message(chat_id, mid)
        except Exception:
            pass


async def handle_account_input(bot: Any, message: Any, lang: str) -> bool:
    """Consumes the user's answer for promo / API key flows. True if handled."""
    user = getattr(message, "from_user", None)
    if user is None:
        return False
    user_id = user.id
    state = ACCOUNT_WAITING.get(user_id)
    if not state:
        return False
    chat_id = message.chat.id
    text = (getattr(message, "text", None) or "").strip()
    ask_id = state.get("ask_id")
    if text.lower() in _CANCEL:
        ACCOUNT_WAITING.pop(user_id, None)
        await _wipe(bot, chat_id, ask_id, message.message_id)
        return True
    kind = str(state.get("kind") or "")
    ACCOUNT_WAITING.pop(user_id, None)
    await _wipe(bot, chat_id, message.message_id)
    if kind == "promo":
        status, detail = promo.redeem("tg", user_id, text)
        body = t(lang, "promo_ok", detail) if status.startswith("ok") else t(lang, "promo_fail", detail)
        if ask_id:
            await _edit_plain(bot, chat_id, ask_id, f"# {t(lang, 'promo_title')}\n\n---\n\n{body}")
        return True
    if kind == "api_name":
        if not cloud.enabled():
            if ask_id:
                await _edit_plain(bot, chat_id, ask_id, f"# {t(lang, 'api_title')}\n\n---\n\n{t(lang, 'api_hint')}")
            return True
        acct = cloud.resolve("tg", user_id)
        created = cloud.create_api_key(acct, text or "Ключ")
        if not created or created.get("error"):
            body = t(lang, "api_limit") if (created or {}).get("error") == "limit" else t(lang, "api_hint")
            if ask_id:
                await _edit_plain(bot, chat_id, ask_id, f"# {t(lang, 'api_title')}\n\n---\n\n{body}")
            return True
        if ask_id:
            await _edit_plain(
                bot, chat_id, ask_id,
                f"# {t(lang, 'api_title')}\n\n---\n\n{t(lang, 'api_created', created.get('secret'))}",
            )
        return True
    if kind == "api_revoke":
        acct = cloud.resolve("tg", user_id)
        keys = cloud.list_api_keys(acct)
        try:
            idx = int(text) - 1
        except ValueError:
            idx = -1
        if 0 <= idx < len(keys):
            cloud.revoke_api_key(acct, str(keys[idx].get("id")))
            body = t(lang, "api_revoked")
        else:
            body = t(lang, "api_bad")
        if ask_id:
            await _edit_plain(bot, chat_id, ask_id, f"# {t(lang, 'api_title')}\n\n---\n\n{body}")
        return True
    return False
