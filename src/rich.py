# Kulsh GPT | v2.45.0
# by (main author): starfall-apk
# coauthor & bot hosting: pomidorka1515

"""Telegram rich messages, HTML fallback, typing indicator, apply animation."""

import asyncio
import re
from typing import Any, cast

import aiohttp
from telebot import types as types
from telebot.types import InlineKeyboardMarkup

from src.util import (
    TG_TOKEN,
    JsonDict,
    html_to_md,
    json_dict,
    calc_typing_delay,
    config_children_msgs,
    logger,
    markdown_like_to_telegram_html,
)
import src.util as state

tg_bot: Any = None


def bind(bot: Any) -> None:
    global tg_bot
    tg_bot = bot


async def send_tg_html(chat_id: int, text: str, reply_to: int | None = None) -> None:
    html_text = markdown_like_to_telegram_html(text)
    chunks = [html_text[i:i + 4000] for i in range(0, max(len(html_text), 1), 4000)]
    for i, chunk in enumerate(chunks):
        try:
            if i == 0 and reply_to is not None:
                await tg_bot.send_message(chat_id, chunk, parse_mode='HTML',
                                          reply_to_message_id=reply_to)
            else:
                await tg_bot.send_message(chat_id, chunk, parse_mode='HTML')
        except Exception as e:
            logger.warning(f"HTML-отправка не удалась, plain: {e}")
            plain = re.sub(r'<[^>]+>', '', chunk)
            try:
                if i == 0 and reply_to is not None:
                    await tg_bot.send_message(chat_id, plain, reply_to_message_id=reply_to)
                else:
                    await tg_bot.send_message(chat_id, plain)
            except Exception as e2:
                logger.error(f"plain fallback fail: {e2}")


async def reply_tg_html(message: types.Message, text: str) -> None:
    await send_tg_html(message.chat.id, text, reply_to=message.message_id)


async def typing_with_delay_tg(chat_id: int, text: str, delay: float | None = None) -> None:
    if delay is None:
        delay = calc_typing_delay(text)
    elapsed = 0.0
    chunk = 4.0
    while elapsed < delay:
        try:
            await tg_bot.send_chat_action(chat_id, 'typing')
        except Exception as e:
            logger.debug(f"typing action: {e}")
        step = min(chunk, delay - elapsed)
        await asyncio.sleep(step)
        elapsed += step


# ============================================================
# RICH MESSAGE
# ============================================================
def parse_inline(text: str) -> Any:
    if not text:
        return ""
    text = html_to_md(text)
    parts: list[Any] = []
    buf = ""

    def flush() -> None:
        nonlocal buf
        if buf:
            parts.append(buf)
            buf = ""

    i = 0
    n = len(text)
    while i < n:
        if text.startswith("**", i):
            end = text.find("**", i + 2)
            if end != -1:
                flush()
                parts.append({"type": "bold", "text": parse_inline(text[i + 2:end])})
                i = end + 2
                continue
        if text.startswith("__", i):
            end = text.find("__", i + 2)
            if end != -1:
                flush()
                parts.append({"type": "underline", "text": parse_inline(text[i + 2:end])})
                i = end + 2
                continue
        if text.startswith("~~", i):
            end = text.find("~~", i + 2)
            if end != -1:
                flush()
                parts.append({"type": "strikethrough", "text": parse_inline(text[i + 2:end])})
                i = end + 2
                continue
        if text.startswith("$$", i):
            end = text.find("$$", i + 2)
            if end != -1:
                flush()
                parts.append({"type": "mathematical_expression", "expression": text[i + 2:end]})
                i = end + 2
                continue
        if text[i] == "*" and not text.startswith("**", i):
            end = text.find("*", i + 1)
            if end != -1 and not text.startswith("**", end):
                flush()
                parts.append({"type": "italic", "text": parse_inline(text[i + 1:end])})
                i = end + 1
                continue
        if text[i] == "_" and not text.startswith("__", i):
            end = text.find("_", i + 1)
            if end != -1 and not text.startswith("__", end):
                flush()
                parts.append({"type": "italic", "text": parse_inline(text[i + 1:end])})
                i = end + 1
                continue
        if text[i] == "`":
            end = text.find("`", i + 1)
            if end != -1:
                flush()
                parts.append({"type": "code", "text": text[i + 1:end]})
                i = end + 1
                continue
        if text[i] == "[":
            m = re.match(r'\[([^\]]+)\]\(([^)]+)\)', text[i:])
            if m:
                flush()
                parts.append({"type": "url", "text": m.group(1), "url": m.group(2)})
                i += m.end()
                continue
        buf += text[i]
        i += 1

    flush()
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return parts


def make_cell(raw: str) -> JsonDict:
    """Ячейка таблицы. *...* → is_header=True (залитая). По центру."""
    s = (raw or "").strip()
    is_header = False
    inner = s
    if len(s) >= 2 and s.startswith('*') and s.endswith('*') and '*' not in s[1:-1]:
        inner = s[1:-1]
        is_header = True
    cell: dict[str, Any] = {"text": parse_inline(inner), "align": "center"}
    if is_header:
        cell["is_header"] = True
    return cell


def text_to_blocks(text: str) -> list[JsonDict]:
    if not text:
        return []
    text = html_to_md(text)
    lines = text.split('\n')
    blocks: list[JsonDict] = []
    i = 0
    n = len(lines)
    in_code = False
    code_lang = ""
    code_lines: list[str] = []
    table_rows: list[list[JsonDict]] = []

    def flush_code() -> None:
        nonlocal in_code, code_lang, code_lines
        if code_lines:
            block: dict[str, Any] = {"type": "pre", "text": '\n'.join(code_lines)}
            if code_lang:
                block["language"] = code_lang
            blocks.append(block)
        in_code = False
        code_lang = ""
        code_lines = []

    def flush_table() -> None:
        nonlocal table_rows
        if table_rows:
            blocks.append({
                "type": "table",
                "cells": table_rows,
                "is_bordered": True,
            })
        table_rows = []

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith('```'):
            if not in_code:
                in_code = True
                code_lang = stripped[3:].strip()
                code_lines = []
            else:
                flush_code()
            i += 1
            continue
        if in_code:
            code_lines.append(line)
            i += 1
            continue

        if stripped.startswith('|') and stripped.endswith('|') and len(stripped) >= 2:
            inner = stripped.strip('|')
            cells_raw = inner.split('|')
            if cells_raw and all(re.match(r'^\s*:?-+:?\s*$', c) for c in cells_raw):
                i += 1
                continue
            table_rows.append([make_cell(c) for c in cells_raw])
            i += 1
            continue
        else:
            flush_table()

        m = re.match(r'^(#{1,6})\s+(.*)', line)
        if m:
            level = len(m.group(1))
            blocks.append({
                "type": "heading",
                "text": parse_inline(m.group(2)),
                "size": level,
            })
            i += 1
            continue

        if re.match(r'^-{3,}$', stripped) or re.match(r'^\*{3,}$', stripped):
            blocks.append({"type": "divider"})
            i += 1
            continue

        if re.match(r'^-\s*\[[ x]\]', line):
            items: list[JsonDict] = []
            while i < n and re.match(r'^-\s*\[[ x]\]', lines[i]):
                checked = '[x]' in lines[i].lower()
                item_text = re.sub(r'^-\s*\[[ x]\]\s*', '', lines[i])
                item: dict[str, Any] = {
                    "blocks": [{"type": "paragraph", "text": parse_inline(item_text)}],
                    "has_checkbox": True,
                }
                if checked:
                    item["is_checked"] = True
                items.append(item)
                i += 1
            blocks.append({"type": "list", "items": items})
            continue

        if re.match(r'^[-*+]\s', line):
            bullet_items: list[JsonDict] = []
            while i < n and re.match(r'^[-*+]\s', lines[i]):
                item_text = re.sub(r'^[-*+]\s', '', lines[i])
                bullet_items.append({
                    "blocks": [{"type": "paragraph", "text": parse_inline(item_text)}],
                })
                i += 1
            blocks.append({"type": "list", "items": bullet_items})
            continue

        if re.match(r'^\d+\.\s', line):
            numbered_items: list[JsonDict] = []
            while i < n and re.match(r'^\d+\.\s', lines[i]):
                item_text = re.sub(r'^\d+\.\s', '', lines[i])
                numbered_items.append({
                    "blocks": [{"type": "paragraph", "text": parse_inline(item_text)}],
                })
                i += 1
            blocks.append({"type": "list", "items": numbered_items})
            continue

        if stripped.startswith('>'):
            quote_lines: list[str] = []
            while i < n and lines[i].strip().startswith('>'):
                quote_lines.append(lines[i].strip()[1:].strip())
                i += 1
            blocks.append({
                "type": "blockquote",
                "blocks": [{"type": "paragraph", "text": parse_inline(' '.join(quote_lines))}],
            })
            continue

        if not stripped:
            i += 1
            continue

        blocks.append({
            "type": "paragraph",
            "text": parse_inline(line),
        })
        i += 1

    flush_code()
    flush_table()
    return blocks


def looks_like_rich(text: str) -> bool:
    if not text:
        return False
    return bool(
        re.search(r'^#{1,6}\s', text, re.MULTILINE) or
        re.search(r'^\|.*\|', text, re.MULTILINE) or
        re.search(r'^[-*+]\s', text, re.MULTILINE) or
        re.search(r'^\d+\.\s', text, re.MULTILINE) or
        re.search(r'^-\s*\[[ x]\]', text, re.MULTILINE) or
        re.search(r'^>\s', text, re.MULTILINE) or
        '```' in text or
        re.search(r'\$\$.+?\$\$', text, re.DOTALL) or
        re.search(r'<(b|strong|i|em|u|ins|s|strike|del|code|pre|a)\b', text, re.IGNORECASE) or
        re.search(r'^-{3,}\s*$', text, re.MULTILINE) or
        re.search(r'^\*{3,}\s*$', text, re.MULTILINE)
    )


def build_rich_message(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    if not looks_like_rich(text):
        return None
    try:
        blocks = text_to_blocks(text)
    except Exception as e:
        logger.warning(f"build_rich_message parse error: {e}")
        return None
    if not blocks:
        return None
    return {
        "blocks": blocks,
        "is_rtl": False,
        "skip_entity_detection": False,
    }


def is_button_type_error(err_text: str) -> bool:
    return "BUTTON_TYPE_INVALID" in err_text


async def send_rich_message(
    chat_id: int,
    text: str,
    reply_to: int | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
    if not state.premium_functions_enabled:
        return False
    rich = build_rich_message(text)
    if not rich:
        return False

    async def _try_post(markup: InlineKeyboardMarkup | None) -> tuple[int, str]:
        payload: dict[str, Any] = {"chat_id": chat_id, "rich_message": rich}
        if reply_to:
            payload["reply_parameters"] = {"message_id": reply_to}
        if markup is not None:
            try:
                payload["reply_markup"] = json_dict(cast(Any, markup).to_dict())
            except AttributeError:
                payload["reply_markup"] = markup
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendRichMessage"
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                body = await resp.text()
                return resp.status, body

    try:
        status, body = await _try_post(reply_markup)
        if status == 200:
            return True
        if status == 400 and is_button_type_error(body) and reply_markup is not None:
            logger.warning("sendRichMessage BUTTON_TYPE_INVALID — повтор без клавиатуры")
            status, body = await _try_post(None)
            if status == 200:
                return True
        logger.warning(f"sendRichMessage {status}: {body[:400]}")
        return False
    except Exception as e:
        logger.warning(f"sendRichMessage error: {e}")
        return False


async def send_rich_message_returning_id(
    chat_id: int,
    text: str,
    reply_to: int | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> int | None:
    """Отправляет rich и возвращает message_id, или None."""
    if not state.premium_functions_enabled:
        return None
    rich = build_rich_message(text)
    if not rich:
        return None
    payload: dict[str, Any] = {"chat_id": chat_id, "rich_message": rich}
    if reply_to:
        payload["reply_parameters"] = {"message_id": reply_to}
    if reply_markup is not None:
        try:
            payload["reply_markup"] = json_dict(cast(Any, reply_markup).to_dict())
        except AttributeError:
            payload["reply_markup"] = reply_markup
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendRichMessage"
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                body = await resp.json()
                if resp.status == 200 and body.get("ok"):
                    res = cast(JsonDict, body.get("result") or {})
                    mid = res.get("message_id")
                    if isinstance(mid, int):
                        return mid
                logger.warning(f"sendRichMessage(ret) {resp.status}: {str(body)[:400]}")
    except Exception as e:
        logger.warning(f"send_rich_message_returning_id: {e}")
    return None


async def edit_rich_message(
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
    if not state.premium_functions_enabled:
        return False
    rich = build_rich_message(text)
    if not rich:
        return False

    async def _try_edit(markup: InlineKeyboardMarkup | None) -> tuple[int, str]:
        payload: dict[str, Any] = {"chat_id": chat_id, "message_id": message_id, "rich_message": rich}
        if markup is not None:
            try:
                payload["reply_markup"] = json_dict(cast(Any, markup).to_dict())
            except AttributeError:
                payload["reply_markup"] = markup
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{TG_TOKEN}/editMessageText"
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                body = await resp.text()
                return resp.status, body

    try:
        status, body = await _try_edit(reply_markup)
        if status == 200:
            return True
        if status == 400 and is_button_type_error(body) and reply_markup is not None:
            logger.warning("editMessageText(rich) BUTTON_TYPE_INVALID — повтор без клавиатуры")
            status, body = await _try_edit(None)
            if status == 200:
                return True
        logger.warning(f"editMessageText(rich) {status}: {body[:400]}")
        return False
    except Exception as e:
        logger.warning(f"edit_rich_message error: {e}")
        return False


async def send_formatted(
    chat_id: int,
    text: str,
    reply_to: int | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    sent_ok = await send_rich_message(chat_id, text, reply_to=reply_to, reply_markup=reply_markup)
    if sent_ok:
        return
    html_text = markdown_like_to_telegram_html(text)
    try:
        await tg_bot.send_message(
            chat_id, html_text, parse_mode='HTML',
            reply_to_message_id=reply_to, reply_markup=reply_markup,
        )
    except Exception as e:
        err = str(e)
        if is_button_type_error(err) and reply_markup is not None:
            logger.warning("HTML send BUTTON_TYPE_INVALID — повтор без клавиатуры")
            try:
                await tg_bot.send_message(
                    chat_id, html_text, parse_mode='HTML',
                    reply_to_message_id=reply_to, reply_markup=None,
                )
                return
            except Exception as e2:
                err = str(e2)
        logger.warning(f"html send failed: {err}; trying plain")
        plain = re.sub(r'<[^>]+>', '', html_text)
        try:
            await tg_bot.send_message(
                chat_id, plain, reply_to_message_id=reply_to, reply_markup=reply_markup,
            )
        except Exception as e2:
            if is_button_type_error(str(e2)) and reply_markup is not None:
                try:
                    await tg_bot.send_message(
                        chat_id, plain, reply_to_message_id=reply_to, reply_markup=None,
                    )
                    return
                except Exception as e3:
                    logger.error(f"plain fallback fail: {e3}")
                    return
            logger.error(f"plain fallback fail: {e2}")


async def send_formatted_returning_id(
    chat_id: int,
    text: str,
    reply_to: int | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> int | None:
    """Как send_formatted, но возвращает message_id."""
    mid = await send_rich_message_returning_id(chat_id, text, reply_to=reply_to, reply_markup=reply_markup)
    if mid is not None:
        return mid
    html_text = markdown_like_to_telegram_html(text)
    try:
        msg = await tg_bot.send_message(
            chat_id, html_text, parse_mode='HTML',
            reply_to_message_id=reply_to, reply_markup=reply_markup,
        )
        return getattr(msg, "message_id", None)
    except Exception as e:
        err = str(e)
        logger.warning(f"send_formatted_returning_id: html failed: {err}")
        plain = re.sub(r'<[^>]+>', '', html_text)
        try:
            msg = await tg_bot.send_message(
                chat_id, plain, reply_to_message_id=reply_to, reply_markup=reply_markup,
            )
            return getattr(msg, "message_id", None)
        except Exception as e2:
            logger.error(f"send_formatted_returning_id: plain fail: {e2}")
            return None


async def stream_draft(chat_id: int, draft_id: int, text: str) -> bool:
    if not state.premium_functions_enabled:
        return False
    payload = {"chat_id": chat_id, "draft_id": draft_id, "text": text}
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessageDraft"
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                return resp.status == 200
    except Exception:
        return False


APPLY_ANIMATION_FRAMES = ["🍷🗿", "🗿🍷", "🍷🗿"]


async def edit_plain_safe(chat_id: int, message_id: int, text: str, attempts: int = 3) -> bool:
    for _ in range(attempts):
        try:
            await tg_bot.edit_message_text(text, chat_id, message_id)
            return True
        except Exception as e:
            err = str(e)
            if "message is not modified" in err:
                return True
            if "Too Many Requests" in err or "retry after" in err.lower():
                m = re.search(r'retry after (\d+)', err, re.IGNORECASE)
                wait = float(m.group(1)) if m else 1.0
                await asyncio.sleep(wait)
                continue
            return False
    return False


async def play_apply_animation(chat_id: int, message_id: int, step_delay: float = 0.85) -> None:
    try:
        for frame in APPLY_ANIMATION_FRAMES:
            await edit_plain_safe(chat_id, message_id, frame)
            await asyncio.sleep(step_delay)
        try:
            await tg_bot.delete_message(chat_id, message_id)
        except Exception:
            pass
    except Exception as e:
        logger.debug(f"play_apply_animation: {e}")


async def cleanup_config_children(chat_id: int, user_id: int) -> None:
    keys = list(config_children_msgs.keys())
    for key in keys:
        if key[0] != chat_id or key[1] != user_id:
            continue
        for mid in config_children_msgs.pop(key, []):
            try:
                await tg_bot.delete_message(chat_id, mid)
            except Exception:
                pass
