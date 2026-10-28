# Kulsh GPT | v2.47.0
# by (main author): starf6ll
# coauthor & bot hosting: pomidorka1515

"""Telegram keyboards, callbacks, and message handlers."""

import asyncio
from collections import deque
import json
import random
import re
import time
from typing import Any, cast

from telebot import types as types
from telebot import util as util
from telebot.types import ForceReply, InlineKeyboardMarkup, InputFile

from src import balance_ui
from src import admin_panel
from src.loops import send_donation_alert
from src.ai import (
    extract_search_marker,
    format_search_results,
    ask_ai_async,
    web_search,
    user_wants_chart,
)
from src.charts import extract_chart_marker, render_infographic
from src.draw import process_drawing
from src.looks import (
    create_femboy_battle_infographic,
    create_femboy_infographic,
    get_femboy_battle_data,
    get_femboy_data,
)
from src.rich import (
    cleanup_config_children,
    edit_rich_message,
    play_apply_animation,
    reply_tg_html as reply_tg_html,
    send_formatted,
    send_formatted_returning_id,
    send_rich_message,
    send_tg_html,
    stream_draft,
    typing_with_delay_tg,
)
from src.ui import (
    build_menu_text,
    build_start_text,
    config_text,
    model_picker_text,
    mode_picker_text,
    build_lang_keyboard,
    build_main_config_keyboard,
    build_menu_keyboard,
    build_mode_keyboard,
    build_model_keyboard,
    build_start_keyboard,
    build_theme_keyboard,
)
from src.util import (
    BOT_VERSION,
    BOT_LOG_FILE,
    COMMUNICATION_MODES,
    DONATE_URL,
    GITHUB_URL,
    MINI_APP_URL,
    MODEL_LIST,
    model_display_name,
    PREMIUM_ADMIN_ID,
    REACT_PATTERN,
    STICKER_POOL,
    UTILITY_PATTERNS,
    WHY_PATTERN,
    calc_typing_delay,
    cb_id,
    clean_extra_text,
    clean_json_text,
    extract_reaction_and_why,
    human_uptime,
    markdown_like_to_telegram_html,
    process_ai_response,
    save_user_configs,
    scrub_stray_markers,
    split_emojis,
    strip_chat_emojis,
    strip_chat_punctuation,
    tr,
    tg_msg,
    add_bot_memory,
    add_donation,
    chat_media_history,
    chat_memories,
    config_children_msgs,
    config_msg_owners,
    config_trigger_msgs,
    bind_ui_flow,
    take_ui_flow,
    ui_flow_by_msg,
    get_chat_key,
    get_chat_memory,
    get_user_config,
    last_old_reply,
    last_random_reply,
    logger,
    long_term_memory,
    pending_donations,
    prompt_waiting,
    last_search_sources,
    save_long_term_memory,
)
import src.util as state
tg_bot: Any = None


def _media() -> Any:
    from src import media as media_mod
    return media_mod


async def get_avatar_description_tg(message: types.Message, chat_id: int, user_id: int, lang: str = "ru") -> str | None:
    return cast("str | None", await _media().get_avatar_description_tg(message, chat_id, user_id, lang))


async def get_recall_media_description_tg(
    message: types.Message, chat_id: int, user_id: int, n: int = 3, lang: str = "ru",
) -> str | None:
    return cast("str | None", await _media().get_recall_media_description_tg(message, chat_id, user_id, n, lang))


def bind(bot: Any) -> None:
    global tg_bot
    tg_bot = bot
    from src import rich
    rich.bind(bot)


def _strip_recall_marker(text: str) -> str:
    if not text:
        return text
    pat = UTILITY_PATTERNS.get("recall_media")
    if pat is None:
        return text
    out = pat.sub(' ', text)
    out = re.sub(r'[ \t]{2,}', ' ', out)
    out = re.sub(r'[ \t]+([,.!?;:])(?=[ \t\n]|$)', r'\1', out)
    out = re.sub(r'[ \t]+\n', '\n', out)
    return out.strip()


# ============================================================
# РЕАКЦИИ
# ============================================================
def _tg_bot_id() -> int | None:
    try:
        return tg_bot.user.id if tg_bot and tg_bot.user else None
    except Exception:
        return None


async def _apply_tg_reaction(chat_id: int, message_id: int, emojis_str: str) -> list[str]:
    emojis = split_emojis(emojis_str)
    if not emojis:
        return []
    try:
        from telebot.types import ReactionTypeEmoji
    except Exception:
        ReactionTypeEmoji = None  # type: ignore
    if ReactionTypeEmoji is None:
        logger.warning("ReactionTypeEmoji недоступен в этой версии pyTelegramBotAPI")
        return []
    try:
        reaction_list = [ReactionTypeEmoji(emoji=e) for e in emojis[:1]]
        await tg_bot.set_message_reaction(chat_id, message_id, reaction=reaction_list)
    except Exception as e:
        logger.warning(f"set_message_reaction: {e}")
        return []
    return emojis[:1]


async def _handle_reaction_markers(
    message: types.Message,
    chat_id: int,
    user_id: int,
    text: str,
    cfg: dict[str, Any],
) -> tuple[str, list[str]]:
    if not cfg.get("reactions_enabled", True):
        cleaned, _, _ = extract_reaction_and_why(text)
        return cleaned, []
    cleaned, emojis_str, why_text = extract_reaction_and_why(text or "")
    if not emojis_str:
        return text, []

    target_msg_id = message.message_id
    if message.reply_to_message and message.reply_to_message.message_id:
        target_msg_id = message.reply_to_message.message_id

    bot_id = _tg_bot_id()
    target_from_bot = False
    if target_msg_id != message.message_id and message.reply_to_message and message.reply_to_message.from_user:
        if bot_id and message.reply_to_message.from_user.id == bot_id:
            target_from_bot = True
    if target_msg_id == message.message_id and message.from_user and bot_id and message.from_user.id == bot_id:
        target_from_bot = True

    if target_from_bot:
        logger.info("Пропускаю реакцию: цель — собственное сообщение бота")
        return cleaned, []

    applied = await _apply_tg_reaction(chat_id, target_msg_id, emojis_str)
    if applied and why_text:
        mem_text = f"[реакция {' '.join(applied)}] {why_text}"
        add_bot_memory(f"tg_{chat_id}", mem_text)
        logger.info(f"😀 Реакция {' '.join(applied)} + мысль: {why_text[:80]}")
    elif applied:
        add_bot_memory(f"tg_{chat_id}", f"[реакция {' '.join(applied)}]")
    return cleaned, applied


# ============================================================
# EDIT HELPERS
# ============================================================
async def _edit_config_message(chat_id: int, message_id: int,
                                text: str, kb: InlineKeyboardMarkup) -> bool:
    ok = await edit_rich_message(chat_id, message_id, text, reply_markup=kb)
    if ok:
        return True
    html_text = markdown_like_to_telegram_html(text)
    try:
        await tg_bot.edit_message_text(
            html_text, chat_id, message_id,
            parse_mode='HTML', reply_markup=kb,
        )
        return True
    except Exception as e:
        err = str(e)
        if "message is not modified" in err:
            return True
        logger.warning(f"edit(html) fail: {e}")
        plain = re.sub(r'<[^>]+>', '', html_text)
        try:
            await tg_bot.edit_message_text(plain, chat_id, message_id, reply_markup=kb)
            return True
        except Exception as e2:
            logger.warning(f"edit(plain) fail: {e2}")
            return False


async def edit_or_send(call: types.CallbackQuery, text: str, kb: InlineKeyboardMarkup) -> None:
    msg = tg_msg(call)
    await _edit_config_message(msg.chat.id, msg.message_id, text, kb)


async def dismiss_ui_flow(chat_id: int, user_id: int, bot_message_id: int, *, keep_bot: bool = False) -> None:
    rec = take_ui_flow(bot_message_id) or {}
    origin = rec.get("origin_id")
    extras = rec.get("extra") if isinstance(rec.get("extra"), list) else []
    trig = config_trigger_msgs.pop(get_chat_key("tg", chat_id), None)
    await cleanup_config_children(chat_id, user_id)
    targets: list[tuple[int, int]] = []
    if isinstance(origin, int):
        targets.append((chat_id, origin))
    if isinstance(trig, int) and isinstance(origin, int) and trig != origin:
        targets.append((chat_id, trig))
    for item in extras:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            targets.append((int(item[0]), int(item[1])))
    if not keep_bot:
        targets.append((chat_id, bot_message_id))
    seen: set[tuple[int, int]] = set()
    for cid, mid in targets:
        if not mid or (cid, mid) in seen:
            continue
        seen.add((cid, mid))
        try:
            await tg_bot.delete_message(cid, mid)
        except Exception:
            pass


def _move_ui_flow(old_id: int, new_id: int | None) -> None:
    rec = take_ui_flow(old_id)
    if not rec or not new_id:
        return
    bind_ui_flow(
        new_id, int(rec.get("chat_id") or 0), int(rec.get("user_id") or 0),
        origin_id=rec.get("origin_id") if isinstance(rec.get("origin_id"), int) else None,
        extra=rec.get("extra") if isinstance(rec.get("extra"), list) else None,
    )


# ============================================================
# CALLBACK HANDLER (cfg:)
# ============================================================
def _parse_cfg_callback(data: str) -> tuple[int | None, str, list[str]]:
    """Разбирает callback_data кнопок настроек.

    Новый формат (с owner): cfg:<owner_id>:<action>[:<arg1>][:<arg2>]
    Старый формат (без owner): cfg:<action>[:<arg1>][:<arg2>]

    Возвращает (owner_id или None, action, [arg1, arg2, ...]).
    """
    parts = data.split(":")
    if len(parts) >= 3 and parts[1].isdigit():
        return int(parts[1]), parts[2], parts[3:]
    return None, (parts[1] if len(parts) > 1 else ""), parts[2:]


async def handle_cfg_callback(call: types.CallbackQuery) -> None:
    msg = tg_msg(call)
    data = call.data or ""
    chat_id = msg.chat.id
    user_id = call.from_user.id

    owner_from_cb, action, extra = _parse_cfg_callback(data)

    # Определяем владельца сообщения настроек.
    owner: int | None = owner_from_cb
    if owner is None:
        # Старый формат callback_data — фолбэк на память процесса.
        # Ключ (chat_id, message_id), а не просто message_id — иначе сообщения
        # из разных чатов с одинаковым id перетирают owner друг другу.
        owner = config_msg_owners.get((chat_id, msg.message_id))
    if owner is None:
        # Не знаем, чьё это сообщение — отказываем.
        lang_fallback = get_user_config("tg", chat_id, user_id).get("language", "ru")
        await tg_bot.answer_callback_query(cb_id(call), tr(lang_fallback, "cfg_not_yours"), show_alert=False)
        return
    if owner != user_id:
        lang_fallback = get_user_config("tg", chat_id, user_id).get("language", "ru")
        await tg_bot.answer_callback_query(cb_id(call), tr(lang_fallback, "cfg_not_yours"), show_alert=False)
        return

    cfg = get_user_config("tg", chat_id, user_id)
    lang = cfg.get("language", "ru")
    toast = tr(lang, "cfg_updated")
    is_private = (msg.chat.type == 'private')

    if action == "mode":
        await edit_or_send(call, mode_picker_text("tg", chat_id, user_id, is_private=is_private),
                            build_mode_keyboard("tg", chat_id, user_id, is_private=is_private))
        await tg_bot.answer_callback_query(cb_id(call))
        return

    if action == "mode_set":
        value = extra[0] if extra else "kent"
        if value == "pro" and not is_private:
            await tg_bot.answer_callback_query(cb_id(call), tr(lang, "mode_need_dm"), show_alert=True)
            return
        if value in COMMUNICATION_MODES:
            cfg["communication_mode"] = value
            if value == "assistant":
                toast = tr(lang, "mode_set", tr(lang, "mode_assistant"))
            elif value == "pro":
                toast = tr(lang, "mode_set", tr(lang, "mode_pro"))
            else:
                toast = tr(lang, "mode_set", tr(lang, "mode_kent"))
            save_user_configs()
        await edit_or_send(call, config_text("tg", chat_id, user_id),
                            build_main_config_keyboard("tg", chat_id, user_id))
        await tg_bot.answer_callback_query(cb_id(call), toast)
        return

    if action == "model_set":
        value = extra[0] if extra else "auto"
        if value == "auto":
            cfg["model"] = None
            toast = tr(lang, "cfg_model_auto")
        else:
            try:
                idx = int(value)
                if 0 <= idx < len(MODEL_LIST):
                    cfg["model"] = MODEL_LIST[idx]
                    toast = tr(lang, "cfg_model_set", model_display_name(MODEL_LIST[idx], lang))
            except ValueError:
                pass
        save_user_configs()
        await edit_or_send(call, model_picker_text("tg", chat_id, user_id),
                            build_model_keyboard("tg", chat_id, user_id))
        await tg_bot.answer_callback_query(cb_id(call), toast)
        return

    if action == "model":
        await edit_or_send(call, model_picker_text("tg", chat_id, user_id),
                            build_model_keyboard("tg", chat_id, user_id))
        await tg_bot.answer_callback_query(cb_id(call))
        return

    if action == "model_co":
        try:
            company_index = int(extra[0]) if extra else 0
        except (ValueError, IndexError):
            company_index = 0
        await edit_or_send(call, model_picker_text("tg", chat_id, user_id, company_index),
                            build_model_keyboard("tg", chat_id, user_id, company_index))
        await tg_bot.answer_callback_query(cb_id(call))
        return

    if action in ("model_back", "sub_back"):
        await edit_or_send(call, config_text("tg", chat_id, user_id),
                            build_main_config_keyboard("tg", chat_id, user_id))
        await tg_bot.answer_callback_query(cb_id(call))
        return

    if action == "lang":
        await edit_or_send(call, f"# {tr(lang, 'cfg_lang')}\n\n---\n", build_lang_keyboard("tg", chat_id, user_id))
        await tg_bot.answer_callback_query(cb_id(call))
        return

    if action == "lang_set":
        val = extra[0] if extra else "ru"
        if val in ("ru", "en"):
            cfg["language"] = val
            lang = val
            toast = tr(lang, "cfg_lang_set_ru") if val == "ru" else tr(lang, "cfg_lang_set_en")
            save_user_configs()
        await edit_or_send(call, config_text("tg", chat_id, user_id),
                            build_main_config_keyboard("tg", chat_id, user_id))
        await tg_bot.answer_callback_query(cb_id(call), toast)
        return

    if action == "theme":
        await edit_or_send(call, f"# {tr(lang, 'cfg_theme')}\n\n---\n", build_theme_keyboard("tg", chat_id, user_id))
        await tg_bot.answer_callback_query(cb_id(call))
        return

    if action == "theme_set":
        val = extra[0] if extra else "dark"
        if val in ("dark", "light"):
            cfg["theme"] = val
            toast = tr(lang, "cfg_theme_dark") if val == "dark" else tr(lang, "cfg_theme_light")
            save_user_configs()
        await edit_or_send(call, config_text("tg", chat_id, user_id),
                            build_main_config_keyboard("tg", chat_id, user_id))
        await tg_bot.answer_callback_query(cb_id(call), toast)
        return

    if action == "temp" or action == "temp_set":
        await tg_bot.answer_callback_query(cb_id(call))
        return

    if action == "prompt":
        try:
            sent = await tg_bot.send_message(
                chat_id, tr(lang, "cfg_edit_prompt_ask"),
                parse_mode='HTML', reply_markup=ForceReply(selective=True),
                reply_to_message_id=msg.message_id,
            )
            prompt_waiting[user_id] = sent.message_id
            key = (chat_id, user_id)
            config_children_msgs.setdefault(key, []).append(sent.message_id)
        except Exception as e:
            logger.warning(f"prompt ask fail: {e}")
        await tg_bot.answer_callback_query(cb_id(call))
        return

    if action == "apply":
        config_msg_owners.pop((chat_id, msg.message_id), None)
        await dismiss_ui_flow(chat_id, user_id, msg.message_id, keep_bot=True)
        save_user_configs()
        await tg_bot.answer_callback_query(cb_id(call), tr(lang, "cfg_done"))
        asyncio.create_task(play_apply_animation(chat_id, msg.message_id))
        return

    if action == "separate":
        new_val = not cfg.get("separate_enabled", True)
        if new_val and cfg.get("streaming_enabled", False):
            await tg_bot.answer_callback_query(cb_id(call), tr(lang, "cfg_mutex"), show_alert=False)
            return
        cfg["separate_enabled"] = new_val
        save_user_configs()
    elif action == "streaming":
        if not state.premium_functions_enabled:
            await tg_bot.answer_callback_query(cb_id(call), tr(lang, "cfg_premium_off"), show_alert=False)
            return
        new_val = not cfg.get("streaming_enabled", False)
        if new_val and cfg.get("separate_enabled", True):
            await tg_bot.answer_callback_query(cb_id(call), tr(lang, "cfg_mutex"), show_alert=False)
            return
        cfg["streaming_enabled"] = new_val
        save_user_configs()
    elif action == "stickers":
        cfg["stickers_enabled"] = not cfg.get("stickers_enabled", True)
        save_user_configs()
    elif action == "autoreply":
        cfg["random_reply_enabled"] = not cfg.get("random_reply_enabled", False)
        save_user_configs()
    elif action == "random":
        cfg["random_messages_enabled"] = not cfg.get("random_messages_enabled", True)
        save_user_configs()
    elif action == "websearch":
        cfg["web_search_enabled"] = not cfg.get("web_search_enabled", True)
        save_user_configs()
    elif action == "drawing":
        cfg["drawing_enabled"] = not cfg.get("drawing_enabled", True)
        save_user_configs()
    elif action == "reactions":
        cfg["reactions_enabled"] = not cfg.get("reactions_enabled", True)
        toast = tr(lang, "cfg_reactions_on") if cfg["reactions_enabled"] else tr(lang, "cfg_reactions_off")
        save_user_configs()
    elif action == "reset_prompt":
        cfg["custom_prompt"] = None
        save_user_configs()
        toast = tr(lang, "cfg_prompt_reset")
    elif action == "reset_memory":
        chat_key = f"tg_{chat_id}"
        if chat_key in long_term_memory:
            del long_term_memory[chat_key]
            save_long_term_memory(long_term_memory)
        chat_memories[chat_key] = deque(maxlen=20)
        chat_media_history[chat_key].clear()
        last_random_reply.pop(chat_key, None)
        last_old_reply.pop(chat_key, None)
        toast = tr(lang, "cfg_memory_reset")
        await tg_bot.answer_callback_query(cb_id(call), toast)
        return

    await edit_or_send(call, config_text("tg", chat_id, user_id),
                        build_main_config_keyboard("tg", chat_id, user_id))
    await tg_bot.answer_callback_query(cb_id(call), toast)


# ============================================================
# CALLBACK HANDLER (menu:)
# ============================================================
async def handle_menu_callback(call: types.CallbackQuery) -> None:
    msg = tg_msg(call)
    data = call.data or ""
    action = data.split(":", 1)[1] if ":" in data else ""
    chat_id = msg.chat.id
    user_id = call.from_user.id
    cfg = get_user_config("tg", chat_id, user_id)
    lang = cfg.get("language", "ru")
    is_private = (msg.chat.type == 'private')

    if action in ("balance", "profile", "link", "api", "checkpay", "support", "promo",
                  "api_new", "api_revoke"):
        nick = call.from_user.full_name or call.from_user.username or str(user_id)
        if action in ("balance", "profile", "link", "api"):
            await tg_bot.answer_callback_query(cb_id(call))
            origin = (ui_flow_by_msg.get(msg.message_id) or {}).get("origin_id")
            if is_private and await balance_ui.edit_screen_tg(
                tg_bot, chat_id, msg.message_id, action, lang, user_id, nick,
            ):
                return
            if action == "balance":
                await balance_ui.send_balance_menu_tg(
                    tg_bot, chat_id, user_id, lang, nick, origin_id=origin if isinstance(origin, int) else None,
                )
            elif action == "profile":
                await balance_ui.send_profile_tg(
                    tg_bot, chat_id, user_id, lang, nick, origin_id=origin if isinstance(origin, int) else None,
                )
            else:
                await balance_ui.send_screen_tg(
                    tg_bot, chat_id, user_id, lang, nick, screen=action,
                    origin_id=origin if isinstance(origin, int) else None,
                )
        elif action == "checkpay":
            await tg_bot.answer_callback_query(cb_id(call), tr(lang, "checking"))
            await balance_ui.check_payment_tg(tg_bot, chat_id, user_id, lang)
        elif action == "support":
            await tg_bot.answer_callback_query(cb_id(call))
            await balance_ui.start_support_tg(tg_bot, chat_id, user_id, lang)
        elif action == "promo":
            await tg_bot.answer_callback_query(cb_id(call))
            await balance_ui.start_promo_tg(tg_bot, chat_id, user_id, lang)
        elif action == "api_new":
            await tg_bot.answer_callback_query(cb_id(call))
            await balance_ui.start_api_new_tg(tg_bot, chat_id, user_id, lang)
        elif action == "api_revoke":
            await tg_bot.answer_callback_query(cb_id(call))
            await balance_ui.start_api_revoke_tg(tg_bot, chat_id, user_id, lang)
        return

    if action == "close":
        await dismiss_ui_flow(chat_id, user_id, msg.message_id)
        await tg_bot.answer_callback_query(cb_id(call))
        return

    if action == "settings":
        # Открыть настройки с этого меню. Кнопка "Настройки" в меню открывает
        # СВОИ настройки тому, кто её нажал. Все cfg-кнопки будут нести owner = user_id.
        cfg_text = config_text("tg", chat_id, user_id)
        kb = build_main_config_keyboard("tg", chat_id, user_id)
        ok = await _edit_config_message(chat_id, msg.message_id, cfg_text, kb)
        if ok:
            config_msg_owners[(chat_id, msg.message_id)] = user_id
        await tg_bot.answer_callback_query(cb_id(call))
        return

    if action == "help":
        await tg_bot.answer_callback_query(cb_id(call))
        help_text = tr(lang, "help_body", MINI_APP_URL, GITHUB_URL)
        edited = await edit_rich_message(chat_id, msg.message_id, help_text)
        if not edited:
            try:
                await tg_bot.delete_message(chat_id, msg.message_id)
            except Exception:
                pass
            new_id = await send_formatted_returning_id(chat_id, help_text)
            _move_ui_flow(msg.message_id, new_id)
        return

    if action == "open":
        await tg_bot.answer_callback_query(cb_id(call))
        menu_text = build_menu_text(lang)
        kb = build_menu_keyboard(lang, is_private=is_private)
        edited = await edit_rich_message(chat_id, msg.message_id, menu_text, reply_markup=kb)
        if not edited:
            try:
                await tg_bot.delete_message(chat_id, msg.message_id)
            except Exception:
                pass
            new_id = await send_formatted_returning_id(chat_id, menu_text, reply_markup=kb)
            _move_ui_flow(msg.message_id, new_id)
        return


# ============================================================
# HELP / MENU / START / DONATE / STATUS
# ============================================================
async def handle_start(message: types.Message) -> None:
    args = util.extract_arguments(message.text or "")
    if args and args.startswith('donate_stars_'):
        try:
            stars = int(args.split('_')[-1])
            if stars <= 0:
                raise ValueError
        except (ValueError, IndexError):
            await reply_tg_html(message, "❌ Неверное количество звёзд.")
            return
        pending_donations[message.chat.id] = stars
        prices = [cast(Any, types.LabeledPrice)(label="💎 Поддержать Кульша", amount=stars)]
        await tg_bot.send_invoice(
            chat_id=message.chat.id, title="💎 Донат Кульшу",
            description=f"💖 Поддержка разработки на {stars} ⭐",
            invoice_payload=f"donate_{stars}_stars", provider_token="",
            currency="XTR", prices=prices, start_parameter="donate",
        )
        return

    if message.from_user is None:
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    cfg = get_user_config("tg", chat_id, user_id)
    lang = cfg.get("language", "ru")
    is_private = (message.chat.type == 'private')
    if args in ("balance", "profile") and is_private:
        nick = message.from_user.full_name or message.from_user.username or str(user_id)
        await balance_ui.send_screen_tg(
            tg_bot, chat_id, user_id, lang, nick, screen=args,
            reply_to=message.message_id, origin_id=message.message_id,
        )
        return
    start_text = build_start_text(lang)
    kb = build_start_keyboard(lang, is_private=is_private)
    mid = await send_formatted_returning_id(
        chat_id, start_text, reply_to=message.message_id, reply_markup=kb,
    )
    bind_ui_flow(mid, chat_id, user_id, origin_id=message.message_id)


async def handle_menu(message: types.Message) -> None:
    if message.from_user is None:
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    cfg = get_user_config("tg", chat_id, user_id)
    lang = cfg.get("language", "ru")
    is_private = (message.chat.type == 'private')
    menu_text = build_menu_text(lang)
    kb = build_menu_keyboard(lang, is_private=is_private)
    mid = await send_formatted_returning_id(
        chat_id, menu_text, reply_to=message.message_id, reply_markup=kb,
    )
    bind_ui_flow(mid, chat_id, user_id, origin_id=message.message_id)


async def handle_help(message: types.Message) -> None:
    if message.from_user is None:
        return
    cfg = get_user_config("tg", message.chat.id, message.from_user.id)
    lang = cfg.get("language", "ru")
    help_text = tr(lang, "help_body", MINI_APP_URL, GITHUB_URL)
    try:
        await send_formatted(message.chat.id, help_text, reply_to=message.message_id)
    except Exception:
        await tg_bot.send_message(
            message.chat.id, re.sub(r'<[^>]+>', '', help_text),
            reply_to_message_id=message.message_id,
        )


async def handle_donate(message: types.Message) -> None:
    if message.from_user is None:
        return
    cfg = get_user_config("tg", message.chat.id, message.from_user.id)
    lang = cfg.get("language", "ru")
    text = (
        f"# {tr(lang, 'donate_title')}\n\n---\n\n"
        f"{tr(lang, 'donate_intro')}\n\n"
        f"**{tr(lang, 'donate_methods')}**\n\n"
        f"- {tr(lang, 'donate_online')}: {DONATE_URL}\n"
        f"- {tr(lang, 'donate_stars_hint')}\n\n"
        f"🔗 GitHub: {GITHUB_URL}"
    )
    try:
        await send_formatted(message.chat.id, text, reply_to=message.message_id)
    except Exception:
        await reply_tg_html(message, f"Поддержать Кульша: {DONATE_URL} 🍷🗿")


async def handle_donate_stars(message: types.Message) -> None:
    if message.from_user is None:
        return
    chat_id = message.chat.id
    cfg = get_user_config("tg", chat_id, message.from_user.id)
    lang = cfg.get("language", "ru")
    args = (util.extract_arguments(message.text or "") or "").strip()
    if not args:
        await reply_tg_html(message, tr(lang, "donate_stars_need"))
        return
    try:
        stars = int(args.split()[0])
        if stars <= 0:
            raise ValueError
    except (ValueError, IndexError):
        await reply_tg_html(message, tr(lang, "donate_stars_bad"))
        return
    pending_donations[chat_id] = stars
    prices = [cast(Any, types.LabeledPrice)(label="Поддержать Кульша", amount=stars)]
    try:
        await tg_bot.send_invoice(
            chat_id=chat_id, title="Донат Кульшу",
            description=f"Поддержка разработки на {stars} ⭐",
            invoice_payload=f"donate_{stars}_stars", provider_token="",
            currency="XTR", prices=prices, start_parameter="donate",
            reply_to_message_id=message.message_id,
        )
    except Exception as e:
        logger.error(f"donate_stars invoice fail: {e}")
        await reply_tg_html(message, tr(lang, "donate_invoice_fail", str(e)))


async def handle_balance(message: types.Message) -> None:
    if message.from_user is None:
        return
    cfg = get_user_config("tg", message.chat.id, message.from_user.id)
    lang = cfg.get("language", "ru")
    nick = message.from_user.full_name or message.from_user.username or str(message.from_user.id)
    await balance_ui.send_balance_menu_tg(
        tg_bot, message.chat.id, message.from_user.id, lang, nick,
        reply_to=message.message_id,
        origin_id=message.message_id,
    )


async def handle_profile(message: types.Message) -> None:
    if message.from_user is None:
        return
    cfg = get_user_config("tg", message.chat.id, message.from_user.id)
    lang = cfg.get("language", "ru")
    nick = message.from_user.full_name or message.from_user.username or str(message.from_user.id)
    await balance_ui.send_profile_tg(
        tg_bot, message.chat.id, message.from_user.id, lang, nick,
        reply_to=message.message_id,
        origin_id=message.message_id,
    )


async def handle_support(message: types.Message) -> None:
    if message.from_user is None:
        return
    cfg = get_user_config("tg", message.chat.id, message.from_user.id)
    lang = cfg.get("language", "ru")
    args = (util.extract_arguments(message.text or "") or "").strip()
    if args:
        await balance_ui.submit_support_tg(
            tg_bot, message.from_user.id, message.chat.id, args, lang,
        )
    else:
        await balance_ui.start_support_tg(tg_bot, message.chat.id, message.from_user.id, lang)


async def handle_status(message: types.Message) -> None:
    if message.from_user is None:
        return
    chat_id = message.chat.id
    cfg = get_user_config("tg", chat_id, message.from_user.id)
    lang = cfg.get("language", "ru")
    mode_txt = str(cfg.get("communication_mode", "kent"))
    if mode_txt == "assistant":
        mode_label = tr(lang, "mode_assistant")
    elif mode_txt == "pro":
        mode_label = tr(lang, "mode_pro")
    else:
        mode_label = tr(lang, "mode_kent")
    try:
        proc_load = __import__("os").getloadavg()[0]
    except Exception:
        proc_load = 0.5
    mood = "🍷🗿" if proc_load < 1.0 else ("😎" if proc_load < 2.5 else "🔥")
    text = (
        f"# 🟢 {tr(lang, 'status_title')}\n\n---\n\n"
        f"**{tr(lang, 'status_online')}**\n\n"
        f"- {tr(lang, 'status_uptime')}: `{human_uptime()}`\n"
        f"- {tr(lang, 'status_latency')}: `~{max(1, int(proc_load * 40))} ms`\n"
        f"- {tr(lang, 'status_mode')}: `{mode_label}`\n"
        f"- {tr(lang, 'status_mood')}: `{tr(lang, 'status_mood_value')}`\n\n"
        f"{mood} · v{BOT_VERSION}"
    )
    try:
        await send_formatted(chat_id, text, reply_to=message.message_id)
    except Exception as e:
        logger.warning(f"status send fail: {e}")
        await reply_tg_html(message, f"🟢 {tr(lang, 'status_online')} · {human_uptime()}")


async def handle_toggle_premium(message: types.Message) -> None:
    if message.from_user is None or message.from_user.id != PREMIUM_ADMIN_ID:
        await reply_tg_html(message, "⛔ Нет доступа.")
        return
    state.set_premium_functions_enabled(not state.premium_functions_enabled)
    label = "включены ✅" if state.premium_functions_enabled else "выключены ❌"
    await reply_tg_html(message, f"Расширенные функции: {label}")


async def handle_admin_secret(message: types.Message) -> None:
    if message.from_user is None or not admin_panel.is_admin_tg(message.from_user.id):
        return
    await admin_panel.open_tg(tg_bot, message.chat.id, message.from_user.id, message.message_id)


async def handle_admin_callback(call: types.CallbackQuery) -> None:
    if not admin_panel.is_admin_tg(call.from_user.id):
        try:
            await tg_bot.answer_callback_query(cb_id(call))
        except Exception:
            pass
        return
    await admin_panel.on_tg_callback(tg_bot, call)


async def handle_pre_checkout(pre_checkout: types.PreCheckoutQuery) -> None:
    await tg_bot.answer_pre_checkout_query(pre_checkout.id, ok=True)


async def handle_successful_payment(message: types.Message) -> None:
    if message.successful_payment is None or message.from_user is None:
        return
    payment = message.successful_payment
    user_id = message.chat.id
    try:
        stars = pending_donations.pop(user_id, None) or int(payment.invoice_payload.split('_')[1])
    except Exception:
        stars = 0
    name = message.from_user.full_name or message.from_user.username or str(user_id)
    logger.info(f"{user_id} задонатил {stars} звёзд")
    add_donation('tg', user_id, stars, name)
    await send_donation_alert('tg', name, stars)
    cfg = get_user_config("tg", message.chat.id, user_id)
    lang = cfg.get("language", "ru")
    await reply_tg_html(message, tr(lang, "donate_thanks", stars))


# ============================================================
# CONFIG / AVATAR / RECALL / SEARCH / CHART / FMB
# ============================================================
async def tg_handle_config(message: types.Message) -> None:
    if message.from_user is None:
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    chat_key = get_chat_key("tg", chat_id)
    config_trigger_msgs[chat_key] = message.message_id
    cfg_text = config_text("tg", chat_id, user_id)
    kb = build_main_config_keyboard("tg", chat_id, user_id)
    mid = await send_formatted_returning_id(
        chat_id, cfg_text, reply_to=message.message_id, reply_markup=kb,
    )
    if mid is not None:
        config_msg_owners[(chat_id, mid)] = user_id
        bind_ui_flow(mid, chat_id, user_id, origin_id=message.message_id)
    else:
        try:
            msg = await tg_bot.send_message(
                chat_id, re.sub(r'<[^>]+>', '', markdown_like_to_telegram_html(cfg_text)),
                reply_markup=kb, reply_to_message_id=message.message_id,
            )
            fallback_id = getattr(msg, "message_id", 0)
            config_msg_owners[(chat_id, fallback_id)] = user_id
            bind_ui_flow(fallback_id, chat_id, user_id, origin_id=message.message_id)
        except Exception as e:
            logger.error(f"Config fallback fail: {e}")


async def tg_handle_avatar(message: types.Message, chat_id: int, user_id: int) -> None:
    cfg = get_user_config("tg", chat_id, user_id)
    lang = cfg.get("language", "ru")
    raw = await get_avatar_description_tg(message, chat_id, user_id, lang=lang)
    if not raw:
        await reply_tg_html(message, tr(lang, "avatar_fail"))
        return
    segments = clean_extra_text(raw)
    if not segments:
        await reply_tg_html(message, tr(lang, "avatar_fail"))
        return
    for i, seg in enumerate(segments):
        seg = scrub_stray_markers(seg)
        if not seg:
            continue
        if i == 0:
            await reply_tg_html(message, seg)
        else:
            await send_tg_html(message.chat.id, seg)


async def tg_handle_recall_media(message: types.Message, chat_id: int, user_id: int, parts: list[str]) -> None:
    cfg = get_user_config("tg", chat_id, user_id)
    lang = cfg.get("language", "ru")
    n = 3
    rm_id: int | None = None
    for p in parts:
        if p.isdigit():
            if len(p) >= 6:
                rm_id = int(p)
            else:
                n = min(int(p), 10)
    if rm_id is not None:
        media_bytes, media_kind = await _media().fetch_media_by_id_tg(chat_id, rm_id)
        if media_bytes:
            kind_label = {"photo": "фото", "video": "видео", "animation": "гифку"}.get(media_kind, "медиа")
            prompt = (
                f"Опиши коротко и живо, что на этом {kind_label}, в стиле Кульша. Маленькими буквами. Без маркеров."
            )
            raw: str | None = await ask_ai_async(
                prompt=prompt, image_bytes=media_bytes, image_mime="image/jpeg",
                chat_id=chat_id, user_id=user_id, platform="tg",
            )
            if raw:
                for i, seg in enumerate(clean_extra_text(raw)):
                    seg = scrub_stray_markers(seg)
                    if not seg:
                        continue
                    if i == 0:
                        await reply_tg_html(message, seg)
                    else:
                        await send_tg_html(message.chat.id, seg)
                return
    raw = await get_recall_media_description_tg(message, chat_id, user_id, n, lang=lang)
    if not raw:
        await reply_tg_html(message, tr(lang, "recall_fail"))
        return
    segments = clean_extra_text(raw)
    if not segments:
        await reply_tg_html(message, tr(lang, "recall_fail"))
        return
    for i, seg in enumerate(segments):
        seg = scrub_stray_markers(seg)
        if not seg:
            continue
        if i == 0:
            await reply_tg_html(message, seg)
        else:
            await send_tg_html(message.chat.id, seg)


async def tg_handle_search(message: types.Message, query: str, chat_id: int, user_id: int) -> None:
    cfg = get_user_config("tg", chat_id, user_id)
    lang = cfg.get("language", "ru")
    if not query.strip():
        await reply_tg_html(message, tr(lang, "search_need_query"))
        return
    results = await search_with_anim_tg(chat_id, message.message_id, query)
    if not results:
        await reply_tg_html(message, tr(lang, "search_nothing"))
        return
    last_search_sources[f"tg_{chat_id}"] = results
    context = format_search_results(results)
    prompt = (
        f"Пользователь просит поискать: {query}\n\nНайденные результаты:\n{context}\n\n"
        f"Ответь сам, как расписать — живо и по делу, можно сводкой или парой фраз. "
        f"Ссылки в текст вставлять не обязан, они уже у тебя в контексте."
    )
    answer = await ask_ai_async(prompt=prompt, chat_id=chat_id, user_id=user_id, platform="tg")
    await send_formatted(chat_id, answer or tr(lang, "search_nothing"), reply_to=message.message_id)


async def tg_handle_chart_request(message: types.Message, description: str,
                                  chat_id: int, user_id: int,
                                  user_images: list[bytes] | None = None) -> None:
    cfg = get_user_config("tg", chat_id, user_id)
    lang = cfg.get("language", "ru")
    if not description.strip():
        await reply_tg_html(message, tr(lang, "chart_usage"))
        return
    status = await tg_bot.send_message(chat_id, tr(lang, "chart_building"))
    chart_prompt = (
        f"Сгенерируй JSON-спецификацию инфографики по описанию:\n\n{description}\n\n"
        f"Верни ТОЛЬКО JSON-объект без markdown и без текста вокруг. "
        f'Структура: {{"theme": "dark_modern|light_minimal|ocean|retro", "title": "...", "blocks": [...]}}'
    )
    raw = await ask_ai_async(
        prompt=chart_prompt,
        system_instruction_override="You are a data-visualization JSON generator. Output ONLY valid JSON.",
        chat_id=chat_id, user_id=user_id, platform="tg",
    )
    spec: dict[str, Any] | None = None
    try:
        spec = json.loads(clean_json_text(raw))
    except Exception:
        m = re.search(r'\{[\s\S]*\}', raw or "")
        if m:
            try:
                spec = json.loads(m.group(0))
            except Exception:
                spec = None
    if not isinstance(spec, dict):
        try:
            await tg_bot.edit_message_text(tr(lang, "chart_error", "invalid JSON"), chat_id, status.message_id)
        except Exception:
            pass
        return
    try:
        img = await render_infographic(spec, user_images=user_images)
    except Exception as e:
        logger.error(f"chart render error: {e}")
        try:
            await tg_bot.edit_message_text(tr(lang, "chart_error", str(e)), chat_id, status.message_id)
        except Exception:
            pass
        return
    try:
        await tg_bot.delete_message(chat_id, status.message_id)
    except Exception:
        pass
    try:
        await tg_bot.send_photo(
            chat_id, InputFile(img, file_name="infographic.png"),
            caption=spec.get("title") or tr(lang, "chart_built"),
            reply_to_message_id=message.message_id,
        )
    except Exception as e:
        logger.error(f"chart send error: {e}")
        await reply_tg_html(message, tr(lang, "chart_error", str(e)))


# ============================================================
# FEMBOY RATE
# ============================================================
async def tg_handle_femboy_rate(message: types.Message, chat_id: int, user_id: int,
                                photo_bytes: bytes, caption: str = "") -> None:
    cfg = get_user_config("tg", chat_id, user_id)
    lang = cfg.get("language", "ru")
    status = await tg_bot.send_message(chat_id, tr(lang, "femboy_analyzing"))
    try:
        include_advice = bool("совет" in caption.lower() or "advice" in caption.lower())
        theme = cfg.get("theme", "dark")
        ai_data = await get_femboy_data(photo_bytes, include_advice, lang=lang)
        if "error" in ai_data:
            await tg_bot.edit_message_text(ai_data['error'], chat_id, status.message_id)
            return
        infographic = await create_femboy_infographic(photo_bytes, ai_data, theme=theme, lang=lang)
        report = (
            f"**{tr(lang, 'femboy_title')}**\n\n"
            f"{tr(lang, 'femboy_gender')} {ai_data.get('gender', '?')}\n"
            f"{tr(lang, 'femboy_score')} `{ai_data.get('fmb', '?')}/10.0`\n"
            f"{tr(lang, 'femboy_tier')} `{ai_data.get('tier', '?')}`\n"
        )
        if ai_data.get("potential"):
            report += f"{tr(lang, 'femboy_potential')} `{ai_data['potential']}`\n"
        report += f"\n**{tr(lang, 'femboy_analysis')}**\n{ai_data.get('summary', '')}"
        if include_advice and ai_data.get("advice"):
            report += f"\n\n**{tr(lang, 'femboy_advice')}**\n{ai_data['advice']}"
        try:
            await tg_bot.send_photo(chat_id, InputFile(infographic), caption=tr(lang, "femboy_report"))
        except Exception as e:
            logger.error(f"femboy infographic send: {e}")
        try:
            await send_formatted(chat_id, report, reply_to=message.message_id)
        except Exception:
            await tg_bot.send_message(chat_id, re.sub(r'<[^>]+>', '', report))
        await tg_bot.delete_message(chat_id, status.message_id)
    except Exception as e:
        logger.error(f"femboy rate: {e}")
        await reply_tg_html(message, f"🌋 Ошибка: {e}")


async def tg_process_femboy_album(media_group_id: str, chat_id: int, user_id: int, message: types.Message | None = None) -> None:
    from src.util import battle_photos as bp
    for _ in range(10):
        if media_group_id in bp and len(bp[media_group_id]) >= 2:
            break
        await asyncio.sleep(0.5)
    cfg = get_user_config("tg", chat_id, user_id)
    lang = cfg.get("language", "ru")
    if media_group_id not in bp or len(bp[media_group_id]) < 2:
        bp.pop(media_group_id, None)
        await tg_bot.send_message(chat_id, tr(lang, "femboy_battle_need_photos"))
        return
    photos = bp.pop(media_group_id)
    p1, p2 = photos[:2]
    theme = cfg.get("theme", "dark")
    status = await tg_bot.send_message(chat_id, tr(lang, "femboy_battle_waiting"))
    ai_data = await get_femboy_battle_data(p1, p2, lang=lang)
    if "error" in ai_data:
        await tg_bot.edit_message_text(ai_data['error'], chat_id, status.message_id)
        return
    battle_img = await create_femboy_battle_infographic(p1, p2, ai_data, theme=theme, lang=lang)
    winner_num = str(ai_data.get("winner", "1"))
    winner_label = tr(lang, "femboy_battle_first") if winner_num == "1" else tr(lang, "femboy_battle_second")
    report_text = (
        f"**{tr(lang, 'femboy_battle_title')}**\n\n"
        f"{tr(lang, 'femboy_battle_winner')} **{winner_label}**\n"
        f"{tr(lang, 'femboy_battle_reason')} {ai_data.get('reason', '')}\n\n"
    )
    try:
        await tg_bot.send_photo(chat_id, InputFile(battle_img), caption=tr(lang, "femboy_battle_caption"))
    except Exception as e:
        logger.error(f"femboy battle infra: {e}")
    try:
        await send_formatted(chat_id, report_text, reply_to=message_id_fallback(message))
    except Exception:
        try:
            await tg_bot.send_message(chat_id, re.sub(r'<[^>]+>', '', report_text))
        except Exception:
            pass
    await tg_bot.delete_message(chat_id, status.message_id)


def message_id_fallback(message: types.Message | None) -> int | None:
    return message.message_id if message else None


# ============================================================
# UTILITY / GROUP & USER INFO
# ============================================================
async def execute_utility_tg(message: types.Message, marker: str, chat_id: int, user_id: int) -> None:
    cfg = get_user_config("tg", chat_id, user_id)
    if marker in ("sticker", "gif"):
        if not cfg.get("stickers_enabled", True):
            return
        try:
            await tg_bot.send_sticker(message.chat.id, random.choice(STICKER_POOL))
        except Exception as e:
            logger.error(f"sticker error: {e}")


async def fetch_group_info_tg(chat_id: int, lang: str = "ru") -> str | None:
    try:
        chat = await tg_bot.get_chat(chat_id)
    except Exception as e:
        logger.warning(f"get_chat: {e}")
        return None
    lines: list[str] = []
    title = getattr(chat, "title", None)
    if title:
        lines.append(f"Название: {title}" if lang == "ru" else f"Title: {title}")
    ctype = getattr(chat, "type", "?")
    lines.append(f"Тип: {ctype}" if lang == "ru" else f"Type: {ctype}")
    username = getattr(chat, "username", None)
    if username:
        lines.append(f"@username: @{username}")
    description = getattr(chat, "description", None)
    if description:
        lines.append(("Описание: " if lang == "ru" else "Description: ") + str(description)[:300])
    try:
        count = await tg_bot.get_chat_member_count(chat_id)
        lines.append(("Участников: " if lang == "ru" else "Members: ") + str(count))
    except Exception:
        pass
    if not lines:
        return None
    return "\n".join(lines)


async def fetch_user_info_tg(user_id: int, chat_id: int, lang: str = "ru") -> str | None:
    lines: list[str] = []
    try:
        chat = await tg_bot.get_chat(user_id)
        name = getattr(chat, "first_name", "") or ""
        last = getattr(chat, "last_name", "") or ""
        full = f"{name} {last}".strip()
        if full:
            lines.append(("Имя: " if lang == "ru" else "Name: ") + full)
        uname = getattr(chat, "username", None)
        if uname:
            lines.append(f"@username: @{uname}")
        bio = getattr(chat, "bio", None)
        if bio:
            lines.append(("Описание: " if lang == "ru" else "Bio: ") + str(bio)[:300])
    except Exception as e:
        logger.debug(f"get_chat(user): {e}")
    lines.append(("ID: " if lang == "ru" else "ID: ") + str(user_id))
    try:
        member = await tg_bot.get_chat_member(chat_id, user_id)
        status = getattr(member, "status", "?")
        lines.append(("Статус в чате: " if lang == "ru" else "Chat status: ") + status)
    except Exception:
        pass
    if not lines:
        return None
    return "\n".join(lines)


# ============================================================
# STREAMING
# ============================================================
async def stream_text_via_drafts(chat_id: int, text: str, is_private: bool = True) -> bool:
    if not state.premium_functions_enabled or not is_private:
        return False
    draft_id = random.randint(1, 2 ** 30)
    words = text.split()
    if not words:
        return False
    acc = ""
    chunk_size = max(1, len(words) // 15)
    for i, w in enumerate(words):
        acc = (acc + " " + w).strip()
        if i % chunk_size == 0 or i == len(words) - 1:
            ok = await stream_draft(chat_id, draft_id, acc)
            if not ok:
                return False
            await asyncio.sleep(0.06)
    return True


# ============================================================
# SEND TG AI RESPONSE
# ============================================================
SEARCH_ANIM_EMOJIS = ("🗿", "🍷")


def _host_of(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return (urlparse(url).hostname or "").lstrip("www.")
    except Exception:
        return ""


async def search_with_anim_tg(chat_id: int, reply_to: int | None, query: str) -> list[Any]:
    status = None
    try:
        status = await tg_bot.send_message(chat_id, "🗿 поиск в интернете...", reply_to_message_id=reply_to)
    except Exception:
        status = None
    results = await web_search(query, max_results=6)
    if status is not None:
        domains: list[str] = []
        for r in results:
            h = _host_of(r.get("url", ""))
            if h and h not in domains:
                domains.append(h)
        if not domains:
            domains = ["wikipedia.org", "duckduckgo.com"]
        for h in domains[:5]:
            emoji = random.choice(SEARCH_ANIM_EMOJIS)
            try:
                await tg_bot.edit_message_text(f"{emoji} читаю {h}", chat_id, status.message_id)
            except Exception:
                pass
            await asyncio.sleep(0.6)
        try:
            await tg_bot.delete_message(chat_id, status.message_id)
        except Exception:
            pass
    return results


async def send_tg_ai_response(message: types.Message, chat_id: int, user_id: int,
                              answer_raw: str, user_text: str | None = None,
                              user_images: list[bytes] | None = None) -> None:
    cfg = get_user_config("tg", chat_id, user_id)
    lang = cfg.get("language", "ru")
    separate_enabled = cfg.get("separate_enabled", True)
    streaming = cfg.get("streaming_enabled", False) and state.premium_functions_enabled
    if streaming and separate_enabled:
        streaming = False

    orig_user_text = (user_text or (message.text or message.caption or "")).strip()

    answer_raw, _applied_reactions = await _handle_reaction_markers(message, chat_id, user_id, answer_raw or "", cfg)

    if cfg.get("web_search_enabled", True):
        query, _ = extract_search_marker(answer_raw or "")
        if query:
            results = await search_with_anim_tg(chat_id, message.message_id, query)
            if results:
                last_search_sources[f"tg_{chat_id}"] = results
                context = format_search_results(results)
                follow_prompt = (
                    f"Пользователь спросил: {orig_user_text}\n\n"
                    f"Ты выполнил поиск: {query}\n\nРезультаты:\n{context}\n\n"
                    f"Ответь на основе результатов, живо и по делу. Можешь использовать утилиты (!separate, !draw и др.). "
                    f"Ссылки в текст вставлять не обязан — они уже у бота в контексте."
                )
                answer_raw = await ask_ai_async(prompt=follow_prompt, chat_id=chat_id, user_id=user_id, platform="tg")
            else:
                answer_raw = tr(lang, "search_nothing")

    rm_id: int | None = None
    rm_match = re.search(r'!\s*recall[\s_]*media\s*:?\s*(\d+)', answer_raw or "", re.IGNORECASE)
    if rm_match:
        try:
            rm_id = int(rm_match.group(1))
        except ValueError:
            rm_id = None
    has_recall = bool(UTILITY_PATTERNS["recall_media"].search(answer_raw or "")) or rm_id is not None
    if has_recall:
        media_bytes: bytes | None = None
        media_kind: str = ""
        try:
            if rm_id is not None:
                media_bytes, media_kind = await _media().fetch_media_by_id_tg(chat_id, rm_id)
            else:
                if message.reply_to_message and message.reply_to_message.message_id:
                    media_bytes, media_kind = await _media().fetch_media_by_id_tg(
                        chat_id, message.reply_to_message.message_id
                    )
                if media_bytes is None:
                    media_bytes, media_kind, _ = await _media().fetch_last_media_tg(chat_id)
        except Exception as e:
            logger.warning(f"recall fetch: {e}")
            media_bytes, media_kind = None, ""

        if media_bytes:
            kind_label = {"photo": "фото", "video": "видео", "animation": "гифку"}.get(media_kind, "медиа")
            follow_prompt = (
                f"Пользователь написал: {orig_user_text or 'покажи последнее медиа'}\n\n"
                f"Вот медиа — это {kind_label}. Опиши коротко и живо, что на нём, в стиле Кульша. "
                f"Маленькими буквами. Без маркеров."
            )
            new_answer = await ask_ai_async(
                prompt=follow_prompt, image_bytes=media_bytes, image_mime="image/jpeg",
                chat_id=chat_id, user_id=user_id, platform="tg",
            )
            if new_answer and new_answer.strip():
                answer_raw = new_answer
            else:
                answer_raw = _strip_recall_marker(answer_raw) + "\n" + tr(lang, "recall_fail")
        else:
            answer_raw = _strip_recall_marker(answer_raw) + "\n" + tr(lang, "recall_fail")
        if rm_id is not None:
            answer_raw = re.sub(r'!\s*recall[\s_]*media\s*:?\s*\d+', ' ', answer_raw, flags=re.IGNORECASE)

    gi = UTILITY_PATTERNS["group_info"].search(answer_raw or "")
    ui = UTILITY_PATTERNS["user_info"].search(answer_raw or "")
    if gi:
        info = await fetch_group_info_tg(chat_id, lang=lang)
        answer_raw = UTILITY_PATTERNS["group_info"].sub(' ', answer_raw)
        if info:
            follow_prompt = (
                f"Пользователь попросил инфо о текущей группе. Данные:\n{info}\n\n"
                f"Кратко перескажи в своём стиле. Без маркеров."
            )
        else:
            follow_prompt = "Не удалось получить инфо о группе. Скажи кратко."
        answer_raw = await ask_ai_async(prompt=follow_prompt, chat_id=chat_id, user_id=user_id, platform="tg")
    if ui:
        m_ui = UTILITY_PATTERNS["user_info"].search(answer_raw)
        target_uid = user_id
        if m_ui and m_ui.group(1):
            try:
                target_uid = int(m_ui.group(1))
            except ValueError:
                target_uid = user_id
        info = await fetch_user_info_tg(target_uid, chat_id, lang=lang)
        answer_raw = UTILITY_PATTERNS["user_info"].sub(' ', answer_raw)
        if info:
            follow_prompt = (
                f"Пользователь попросил инфо о пользователе id {target_uid}. Данные:\n{info}\n\n"
                f"Кратко перескажи в своём стиле. Без маркеров."
            )
        else:
            follow_prompt = "Не удалось получить инфо о пользователе. Скажи об этом."
        answer_raw = await ask_ai_async(prompt=follow_prompt, chat_id=chat_id, user_id=user_id, platform="tg")

    if state.premium_functions_enabled:
        chart_spec, remaining = extract_chart_marker(answer_raw or "")
        if chart_spec:
            user_asked_chart = user_wants_chart(orig_user_text)
            if user_asked_chart:
                try:
                    img = await render_infographic(chart_spec, user_images=user_images)
                    try:
                        await tg_bot.send_photo(
                            chat_id, InputFile(img, file_name="infographic.png"),
                            caption=chart_spec.get("title") or tr(lang, "chart_built"),
                            reply_to_message_id=message.message_id,
                        )
                    except Exception as e:
                        logger.error(f"chart send: {e}")
                except Exception as e:
                    logger.error(f"chart render: {e}")
                    answer_raw = remaining + "\n" + tr(lang, "chart_error", str(e))
                    chart_spec = None
            if chart_spec is not None or not user_asked_chart:
                answer_raw = remaining

    draw_png = None
    draw_before = ""
    draw_after = ""
    if cfg.get("drawing_enabled", True) and ("!draw" in (answer_raw or "") or "!term" in (answer_raw or "")):
        try:
            res = await process_drawing(answer_raw or "")
            draw_png, draw_before, draw_after = res.png, res.before, res.after
            if res.status:
                logger.info(f"🎨 draw terminal: {res.status}")
        except Exception as e:
            logger.error(f"tg draw: {e}")

    clean_segments, markers = process_ai_response(
        draw_before if draw_png is not None else answer_raw,
        separate_enabled=separate_enabled,
    )

    extra_segments: list[str] = []
    if "avatar" in markers:
        markers.remove("avatar")
        try:
            ar = await get_avatar_description_tg(message, chat_id, user_id, lang=lang)
            if ar:
                extra_segments.extend(clean_extra_text(ar))
        except Exception as e:
            logger.warning(f"avatar desc failed: {e}")
    if "recall_media" in markers:
        markers.remove("recall_media")

    all_segments = clean_segments + extra_segments

    if draw_png is None and not all_segments:
        fallback = scrub_stray_markers(answer_raw or "").strip()
        if fallback and not markers:
            all_segments = [fallback]
    if draw_png is None and not all_segments:
        for m in markers:
            try:
                await execute_utility_tg(message, m, chat_id, user_id)
            except Exception as e:
                logger.warning(f"utility {m}: {e}")
        return

    is_private_chat = (message.chat.type == 'private')

    async def _send_seg(seg: str, idx: int) -> None:
        seg = scrub_stray_markers(seg)
        if cfg.get("communication_mode", "kent") == "kent":
            seg = strip_chat_emojis(seg)
            seg = strip_chat_punctuation(seg)
        if not seg:
            return
        try:
            await typing_with_delay_tg(message.chat.id, seg, delay=calc_typing_delay(seg, segment_index=idx))
        except Exception:
            pass
        if streaming and idx == 0 and len(seg) > 60 and is_private_chat:
            try:
                await stream_text_via_drafts(message.chat.id, seg, is_private=True)
            except Exception as e:
                logger.debug(f"stream fail: {e}")
        sent_ok = False
        try:
            sent_ok = await send_rich_message(
                message.chat.id, seg,
                reply_to=message.message_id if idx == 0 else None,
            )
        except Exception as e:
            logger.debug(f"rich fail: {e}")
        if not sent_ok:
            try:
                if idx == 0:
                    await send_tg_html(message.chat.id, seg, reply_to=message.message_id)
                else:
                    await send_tg_html(message.chat.id, seg)
            except Exception as e:
                logger.error(f"send_tg_html fail: {e}")
        add_bot_memory(f"tg_{message.chat.id}", seg)

    for i, seg in enumerate(all_segments):
        await _send_seg(seg, i)

    if draw_png is not None:
        after_segments, _after_markers = process_ai_response(draw_after, separate_enabled=separate_enabled)
        caption = ""
        if after_segments:
            caption = scrub_stray_markers(after_segments[0])
            if cfg.get("communication_mode", "kent") == "kent":
                caption = strip_chat_emojis(caption)
                caption = strip_chat_punctuation(caption)
            caption = caption[:1024]
        try:
            await tg_bot.send_photo(
                chat_id, InputFile(draw_png, file_name="drawing.png"),
                caption=caption or None,
                reply_to_message_id=message.message_id,
            )
            add_bot_memory(f"tg_{message.chat.id}", "[нарисовал картинку]" + (f" {caption}" if caption else ""))
        except Exception as e:
            logger.error(f"tg draw send: {e}")
        for j, seg in enumerate(after_segments[1:], start=1):
            await _send_seg(seg, j)

    for m in markers:
        if m in ("sticker", "gif"):
            try:
                await execute_utility_tg(message, m, chat_id, user_id)
            except Exception as e:
                logger.warning(f"utility {m}: {e}")


# ============================================================
# OLD MESSAGE REPLY
# ============================================================
async def maybe_reply_to_old_message_tg(message: types.Message, chat_id: int, user_id: int) -> None:
    try:
        await asyncio.sleep(3)
    except asyncio.CancelledError:
        return
    chat_key = f"tg_{chat_id}"
    now = time.time()
    if now - last_old_reply.get(chat_key, 0) < 600:
        return
    if random.random() > 0.12:
        return
    mem = list(get_chat_memory(chat_key))
    current_msg_id = message.message_id
    candidates = [
        e for e in mem[:-2]
        if e.get("type") == "user" and e.get("text") and e.get("message_id") != current_msg_id
    ]
    if not candidates:
        return
    old = random.choice(candidates)
    try:
        comment = await ask_ai_async(
            prompt=(
                f"Сейчас идёт живая переписка. Ты краем глаза заметил старое сообщение от "
                f"{old.get('display','?')}: \"{old.get('text','')}\". Хочешь коротко по-пацански "
                f"прокомментировать? Если да — одно короткое сообщение в стиле общения со всеми. "
                f"Если не хочешь — ответь ровно 'НЕТ'."
            ),
            system_instruction_override=(
                "Ты Кульш. Если комментируешь — маленькими буквами, живо. Или 'НЕТ'."
            ),
            chat_id=chat_id, user_id=user_id, platform="tg",
        )
        if comment and comment.strip() and comment.strip().upper() != "НЕТ":
            last_old_reply[chat_key] = now
            cfg = get_user_config("tg", chat_id, user_id)
            segments, markers = process_ai_response(comment, separate_enabled=cfg.get("separate_enabled", True))
            old_msg_id = old.get("message_id")
            for i, seg in enumerate(segments):
                seg = scrub_stray_markers(seg)
                if cfg.get("communication_mode", "kent") == "kent":
                    seg = strip_chat_emojis(seg)
                    seg = strip_chat_punctuation(seg)
                if not seg:
                    continue
                try:
                    await typing_with_delay_tg(message.chat.id, seg, delay=calc_typing_delay(seg, segment_index=i))
                except Exception:
                    pass
                if i == 0 and old_msg_id:
                    await send_tg_html(message.chat.id, seg, reply_to=old_msg_id)
                else:
                    await send_tg_html(message.chat.id, seg)
                add_bot_memory(chat_key, seg)
            for m in markers:
                if m in ("sticker", "gif"):
                    try:
                        await execute_utility_tg(message, m, chat_id, user_id)
                    except Exception:
                        pass
    except Exception as e:
        logger.warning(f"old reply tg: {e}")


async def should_random_reply(platform: str, chat_id: int, user_id: int) -> bool:
    cfg = get_user_config(platform, chat_id, user_id)
    if not cfg.get("random_reply_enabled", False):
        return False
    chat_key = f"{platform}_{chat_id}"
    now = time.time()
    if now - last_random_reply.get(chat_key, 0) < 900:
        return False
    if random.random() > 0.03:
        return False
    return True