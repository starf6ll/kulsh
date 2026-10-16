# Kulsh GPT | v2.47.0
# by (main author): starfall-apk
# coauthor & bot hosting: pomidorka1515

"""Telegram media handler: photos, videos, looksmaxxing, femboy, battle albums, tools."""

import asyncio
import html
import re
import time
from typing import Any

from telebot import types as types
from telebot.types import InputFile

from src.ai import ask_ai_async, extract_memory
from src.looks import (
    create_battle_infographic,
    create_infographic,
    get_battle_data,
    get_looksmaxxing_data,
)


def _tg() -> Any:
    from src import telegram as tg
    return tg


def tg_bot_id() -> int | None:
    try:
        return _tg().tg_bot.user.id if _tg().tg_bot.user else None
    except Exception:
        return None


def resolve_avatar_target_tg(message: types.Message) -> types.User | None:
    bot_id = tg_bot_id()
    if message.reply_to_message and message.reply_to_message.from_user:
        rt = message.reply_to_message.from_user
        if bot_id is None or rt.id != bot_id:
            return rt
    for ent in (message.entities or []):
        if ent.type == "text_mention" and ent.user:
            if bot_id is None or ent.user.id != bot_id:
                return ent.user
    if message.from_user and (bot_id is None or message.from_user.id != bot_id):
        return message.from_user
    return None


async def get_avatar_description_tg(
    message: types.Message, chat_id: int, user_id: int, lang: str = "ru",
) -> str | None:
    target = resolve_avatar_target_tg(message)
    if target is None:
        return None
    name = target.full_name or ("человек" if lang == "ru" else "user")
    uname = f"@{target.username}" if target.username else ""
    try:
        photos = await _tg().tg_bot.get_user_profile_photos(target.id, limit=1)
    except Exception as e:
        logger.warning(f"avatar fetch: {e}")
        return None
    if not (photos.total_count > 0 and photos.photos):
        return tr(lang, "avatar_none", name)
    try:
        file_id = photos.photos[0][-1].file_id
        img_bytes = await get_tg_file_bytes(_tg().tg_bot, file_id)
        prompt = (
            f"Ты только что посмотрел аватарку пользователя {name} {uname}. "
            f"Опиши коротко (1-2 предложения) в стиле Кульша. Без markdown. "
            f"НЕ используй маркеры !separate, !avatar, !recall_media, !sticker, !gif, !search, !chart, !react, !why."
            if lang == "ru" else
            f"You've just seen the avatar of {name} {uname}. Describe briefly. No markers."
        )
        return json_str(await ask_ai_async(
            prompt=prompt, image_bytes=img_bytes, image_mime="image/jpeg",
            chat_id=chat_id, user_id=user_id, platform="tg",
        )) or None
    except Exception as e:
        logger.warning(f"avatar desc: {e}")
        return None


async def fetch_last_media_tg(chat_id: int) -> tuple[bytes | None, str, int | None]:
    """Возвращает (байты, тип, message_id) для последнего реально скачиваемого медиа."""
    history = list(chat_media_history.get(f"tg_{chat_id}", []))
    if not history:
        return None, "", None
    for item in reversed(history):
        fid = item.get("file_id")
        mtype = str(item.get("type") or "")
        mid = item.get("message_id")
        if not fid:
            continue
        try:
            if mtype == "photo":
                b = await get_tg_file_bytes(_tg().tg_bot, fid)
                if b:
                    return b, "photo", mid
            elif mtype in ("video", "animation"):
                raw = await get_tg_file_bytes(_tg().tg_bot, fid)
                frame = await extract_video_frame(raw, ".mp4")
                if frame:
                    return frame, mtype, mid
        except Exception as e:
            logger.warning(f"fetch_last_media ({mtype}): {e}")
            continue
    return None, "", None


async def fetch_media_by_id_tg(chat_id: int, message_id: int) -> tuple[bytes | None, str]:
    """Возвращает (байты, тип) для медиа с конкретным message_id."""
    from src.util import find_media_by_message_id
    item = find_media_by_message_id(f"tg_{chat_id}", message_id)
    if not item:
        return None, ""
    fid = item.get("file_id")
    mtype = str(item.get("type") or "")
    if not fid:
        return None, ""
    try:
        if mtype == "photo":
            b = await get_tg_file_bytes(_tg().tg_bot, fid)
            return (b, "photo") if b else (None, "")
        elif mtype in ("video", "animation"):
            raw = await get_tg_file_bytes(_tg().tg_bot, fid)
            frame = await extract_video_frame(raw, ".mp4")
            return (frame, mtype) if frame else (None, "")
    except Exception as e:
        logger.warning(f"fetch_media_by_id: {e}")
    return None, ""


async def get_recall_media_description_tg(
    message: types.Message, chat_id: int, user_id: int, n: int = 3, lang: str = "ru",
) -> str | None:
    """Резервный путь — если бот вызвал !recall_media из обычного чата, а не через send_tg_ai_response."""
    img_bytes, img_kind, _ = await fetch_last_media_tg(chat_id)
    if img_bytes is None:
        return None
    try:
        kind_label = {"photo": "фото", "video": "видео", "animation": "гифку"}.get(img_kind, "медиа")
        prompt = (
            f"Последнее медиа в чате — это {kind_label}. Опиши коротко, что на нём, в стиле Кульша. "
            f"Без markdown. НЕ используй маркеры !separate, !avatar, !recall_media, !sticker, !gif, !search, !chart, !react."
            if lang == "ru" else
            f"Last media — a {img_kind}. Describe briefly. No markers."
        )
        return json_str(await ask_ai_async(
            prompt=prompt, image_bytes=img_bytes, image_mime="image/jpeg",
            chat_id=chat_id, user_id=user_id, platform="tg",
        )) or None
    except Exception as e:
        logger.warning(f"recall image: {e}")
        return None


from src.tools import tool_edit_archive, tool_review_file
from src.util import (
    json_str,
    tr,
    add_bot_memory,
    add_media_history,
    add_user_memory,
    battle_media_groups,
    battle_photos,
    extract_video_frame,
    get_chat_memory,
    get_tg_file_bytes,
    get_user_config,
    save_user_configs,
    is_battle_command,
    is_femboy_battle_command,
    is_femboy_rate_command,
    is_looksmaxxing_command,
    last_bot_reply,
    last_random_reply,
    logger,
    memory_to_messages,
    user_femboy_state,
    user_looksmaxxing_state,

    COST_ARCHIVE_EDIT,
    DAILY_CREDITS,
    DONATE_URL,
    LOG_INTRO,
    PREMIUM_ADMIN_ID,
    TEXT_EXTS,
    chat_media_history,
    get_top_donators,
    get_user_credits,
    prompt_waiting,
    read_log_tail,
    spend_credits,
    chunk_text,
)


def _is_addressed_from_bot_tg(message: types.Message) -> bool:
    bot_id = tg_bot_id()
    reply_ok = bool(
        message.reply_to_message and message.reply_to_message.from_user
        and message.reply_to_message.from_user.id == bot_id
    )
    text = (message.text or message.caption or "")
    mentions_kulsh = bool(re.search(r'(?i)\bкульш\b', text))
    mentions_uname = False
    try:
        uname = _tg().tg_bot.user.username if _tg().tg_bot.user else None
        if uname and f"@{uname}".lower() in text.lower():
            mentions_uname = True
    except Exception:
        pass
    return reply_ok or mentions_kulsh or mentions_uname


# ============================================================
# MEDIA HANDLER
# ============================================================
async def handle_tg_media(message: types.Message) -> None:
    if message.from_user is None:
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    cfg = get_user_config("tg", chat_id, user_id)
    lang = cfg.get("language", "ru")
    is_dm = message.chat.type == 'private'
    caption = message.caption or ""
    cl = caption.lower()
    chat_key = f"tg_{chat_id}"

    display_name = message.from_user.full_name or "Unknown"
    username = message.from_user.username or ""

    # Обработка ботов
    if message.from_user.is_bot:
        if not _is_addressed_from_bot_tg(message):
            return
        now = time.time()
        if now - last_bot_reply.get(chat_key, 0) < 8:
            return
        last_bot_reply[chat_key] = now

    media_tag = None
    file_id = None
    media_type = None
    file_name = None
    if message.photo:
        file_id = message.photo[-1].file_id
        media_type = "photo"
        media_tag = "[фото]" if lang == "ru" else "[photo]"
    elif message.video:
        file_id = message.video.file_id
        media_type = "video"
        media_tag = "[видео]" if lang == "ru" else "[video]"
    elif message.animation:
        file_id = message.animation.file_id
        media_type = "animation"
        media_tag = "[гифка]" if lang == "ru" else "[gif]"
    elif message.document:
        file_id = message.document.file_id
        media_type = "document"
        file_name = message.document.file_name or "file"
        media_tag = f"[док: {file_name}]" if lang == "ru" else f"[doc: {file_name}]"
    elif message.sticker:
        file_id = message.sticker.file_id
        media_type = "sticker"
        media_tag = "[стикер]" if lang == "ru" else "[sticker]"

    # ВАЖНО: сохраняем message_id, чтобы бот мог ссылаться на конкретное медиа
    if file_id and media_tag:
        add_media_history(
            chat_key, None, media_type or "media", display_name,
            file_id=file_id, caption=caption,
            message_id=message.message_id,
        )

    # FEMBOY BATTLE
    if is_femboy_battle_command(caption) and message.photo:
        if message.media_group_id:
            mgid = message.media_group_id
            if mgid not in battle_photos:
                battle_photos[mgid] = []
                battle_media_groups[mgid] = asyncio.create_task(
                    _tg().tg_process_femboy_album(mgid, chat_id, user_id, message)
                )
            img_bytes = await get_tg_file_bytes(_tg().tg_bot, message.photo[-1].file_id)
            battle_photos[mgid].append(img_bytes)
        else:
            await _tg().reply_tg_html(message, tr(lang, "femboy_battle_need_photos"))
        return

    if message.media_group_id and message.media_group_id in battle_photos and message.photo:
        img_bytes = await get_tg_file_bytes(_tg().tg_bot, message.photo[-1].file_id)
        battle_photos[message.media_group_id].append(img_bytes)
        return

    # PSL BATTLE
    if is_battle_command(caption) and message.photo:
        if message.media_group_id:
            mgid = message.media_group_id
            if mgid not in battle_photos:
                battle_photos[mgid] = []
                battle_media_groups[mgid] = asyncio.create_task(
                    process_battle_media_group(mgid, chat_id, user_id)
                )
            img_bytes = await get_tg_file_bytes(_tg().tg_bot, message.photo[-1].file_id)
            battle_photos[mgid].append(img_bytes)
        else:
            await _tg().reply_tg_html(message, tr(lang, "battle_need_photos"))
        return

    # CHART
    if is_dm or re.search(r'(?i)\bкульш\s+(график|chart|инфографика)', caption or ""):
        m = re.match(r'(?i)кульш\s+(график|chart|инфографика)\s*(.*)', caption or "", re.DOTALL)
        if m and message.photo:
            try:
                img_bytes = await get_tg_file_bytes(_tg().tg_bot, message.photo[-1].file_id)
                await _tg().tg_handle_chart_request(message, m.group(2).strip() or "инфографика с этим фото",
                                              chat_id, user_id, user_images=[img_bytes])
            except Exception as e:
                logger.error(f"chart with user image err: {e}")
            return

    # FEMBOY RATE
    is_femboy = (
        is_femboy_rate_command(caption) or
        (message.reply_to_message and message.reply_to_message.from_user
         and message.reply_to_message.from_user.id == (tg_bot_id() or 0)
         and message.reply_to_message.text
         and is_femboy_rate_command(message.reply_to_message.text)) or
        user_femboy_state.get(chat_id, False)
    )
    if is_femboy and message.photo:
        user_femboy_state[chat_id] = False
        try:
            img_bytes = await get_tg_file_bytes(_tg().tg_bot, message.photo[-1].file_id)
            await _tg().tg_handle_femboy_rate(message, chat_id, user_id, img_bytes, caption)
            add_user_memory(chat_key, "TG", display_name, username, user_id,
                            f"[femboy] {caption}", ["photo"], message_id=message.message_id)
            add_bot_memory(chat_key, "[femboy отчёт]")
        except Exception as e:
            logger.error(f"femboy rate: {e}")
            await _tg().reply_tg_html(message, f"🌋 Ошибка: {e}")
        return

    # PSL
    is_looksmaxxing = (
        is_looksmaxxing_command(caption) or
        (message.reply_to_message and message.reply_to_message.from_user
         and message.reply_to_message.from_user.id == (tg_bot_id() or 0)
         and message.reply_to_message.text
         and is_looksmaxxing_command(message.reply_to_message.text)) or
        user_looksmaxxing_state.get(chat_id, False)
    )
    if is_looksmaxxing and message.photo:
        user_looksmaxxing_state[chat_id] = False
        status = await _tg().tg_bot.send_message(chat_id, tr(lang, "psl_analyzing"))
        try:
            img_bytes = await get_tg_file_bytes(_tg().tg_bot, message.photo[-1].file_id)
            reply_text = message.reply_to_message.text if message.reply_to_message else None
            include_advice = bool(
                "совет" in cl or "advice" in cl or
                (reply_text and ("совет" in reply_text.lower() or "advice" in reply_text.lower()))
            )
            theme = cfg.get("theme", "dark")
            ai_data = await get_looksmaxxing_data(
                img_bytes, include_advice, lang=lang, chat_id=chat_id, user_id=user_id, platform="tg",
            )
            if ai_data.get("not_a_face"):
                await _tg().tg_bot.edit_message_text(ai_data.get("message", tr(lang, "psl_not_a_face")),
                                                     chat_id, status.message_id)
                return
            if "error" in ai_data:
                await _tg().tg_bot.edit_message_text(ai_data['error'], chat_id, status.message_id)
                return
            infographic = await create_infographic(img_bytes, ai_data, theme=theme, lang=lang)
            report_text = (
                f"<b>{tr(lang, 'psl_title')}</b>\n\n"
                f"{tr(lang, 'psl_gender')} {ai_data.get('gender', '?')}\n"
                f"{tr(lang, 'psl_score')} <code>{ai_data.get('psl', '?')}/8.0</code>\n"
                f"{tr(lang, 'psl_tier')} <code>{ai_data.get('tier', '?')}</code>\n"
            )
            if ai_data.get("potential"):
                report_text += f"{tr(lang, 'psl_potential')} <code>{ai_data['potential']}</code>\n"
            report_text += f"\n<b>{tr(lang, 'psl_analysis')}</b>\n{html.escape(ai_data.get('summary', ''))}"
            if include_advice and ai_data.get("advice"):
                report_text += f"\n\n<b>{tr(lang, 'psl_advice')}</b>\n{html.escape(ai_data['advice'])}"
            try:
                await _tg().tg_bot.send_photo(chat_id, InputFile(infographic), caption=tr(lang, "psl_report"))
            except Exception as e:
                logger.error(f"infographic send: {e}")
            for chunk in [report_text[i:i + 3900] for i in range(0, len(report_text), 3900)]:
                try:
                    await _tg().tg_bot.send_message(chat_id, chunk, parse_mode='HTML')
                except Exception:
                    await _tg().tg_bot.send_message(chat_id, re.sub(r'<[^>]+>', '', chunk))
            await _tg().tg_bot.delete_message(chat_id, status.message_id)
            add_user_memory(chat_key, "TG", display_name, username, user_id,
                            f"[looksmaxxing] {caption}", ["photo"], message_id=message.message_id)
            add_bot_memory(chat_key, "[looksmaxxing отчёт]")
        except Exception as e:
            logger.error(f"looksmaxxing: {e}")
            await _tg().reply_tg_html(message, f"🌋 Ошибка: {e}")
        return

    if is_dm and message.document:
        mime = message.document.mime_type or ""
        doc_name = message.document.file_name or ""
        ext = doc_name.lower().rsplit('.', 1)[-1] if '.' in doc_name else ""
        if ext == "zip":
            credits = get_user_credits("tg", user_id)
            if credits < COST_ARCHIVE_EDIT:
                await _tg().reply_tg_html(message, tr(lang, "tool_no_credits", COST_ARCHIVE_EDIT, credits, DAILY_CREDITS))
                return
            spend_credits("tg", user_id, COST_ARCHIVE_EDIT)
            try:
                file_bytes = await get_tg_file_bytes(_tg().tg_bot, message.document.file_id)
            except Exception as e:
                await _tg().reply_tg_html(message, tr(lang, "tool_download_fail", str(e)))
                return
            default_req = "отредактируй что-нибудь полезное" if lang == "ru" else "edit something useful"
            await tool_edit_archive(message, caption.strip() or default_req, file_bytes, doc_name or "archive.zip")
            return
        if ext in TEXT_EXTS or mime.startswith("text/"):
            try:
                file_bytes = await get_tg_file_bytes(_tg().tg_bot, message.document.file_id)
            except Exception as e:
                await _tg().reply_tg_html(message, tr(lang, "tool_download_fail", str(e)))
                return
            default_req = tr(lang, "tool_review_empty")
            await tool_review_file(message, caption.strip() or default_req, file_bytes, doc_name or "file")
            return

    is_reply_to_bot = (message.reply_to_message and message.reply_to_message.from_user
                       and message.reply_to_message.from_user.id == (tg_bot_id() or 0))
    addressed = bool(is_reply_to_bot or re.search(r'(?i)\bкульш\b', caption) or is_dm)

    if not addressed:
        # Сохраняем в память как "[фото без подписи]" — НЕ подставляем "че на этом?"
        text_for_memory = caption.strip() or f"[{media_tag} без подписи]"
        add_user_memory(chat_key, "TG", display_name, username, user_id, text_for_memory,
                        [media_tag or "медиа"], message_id=message.message_id)
        if await _tg().should_random_reply("tg", chat_id, user_id):
            answer = await ask_ai_async(
                context_type="observer",
                messages=memory_to_messages(get_chat_memory(chat_key)),
                chat_id=chat_id, user_id=user_id, platform="tg",
            )
            if answer and answer.strip() and answer.strip().upper() not in ("НЕТ", "NO"):
                last_random_reply[chat_key] = time.time()
                await _tg().send_tg_ai_response(message, chat_id, user_id, answer)
        return

    # addressed — отправляем картинку в AI
    await _tg().tg_bot.send_chat_action(chat_id, 'typing')
    image_bytes = None
    image_mime = "image/jpeg"
    try:
        if message.photo:
            image_bytes = await get_tg_file_bytes(_tg().tg_bot, message.photo[-1].file_id)
        elif message.animation:
            vid = await get_tg_file_bytes(_tg().tg_bot, message.animation.file_id)
            frame = await extract_video_frame(vid, ".mp4")
            if frame:
                image_bytes = frame
        elif message.video:
            vid = await get_tg_file_bytes(_tg().tg_bot, message.video.file_id)
            frame = await extract_video_frame(vid, ".mp4")
            if frame:
                image_bytes = frame
        elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
            image_bytes = await get_tg_file_bytes(_tg().tg_bot, message.document.file_id)
            image_mime = message.document.mime_type
    except Exception as e:
        logger.warning(f"download media: {e}")

    # Если подписи нет — НЕ подставляем "че на этом?". Просто описание.
    if caption.strip():
        prompt = caption.strip()
    else:
        prompt = ""  # пусто = бот сам решит что сказать, глядя на фото

    add_user_memory(chat_key, "TG", display_name, username, user_id,
                    f"{prompt or '[медиа без подписи]'} [с медиа: {media_tag}]", [media_tag or "медиа"],
                    message_id=message.message_id)
    messages = memory_to_messages(get_chat_memory(chat_key))
    answer = await ask_ai_async(messages=messages, image_bytes=image_bytes,
                                image_mime=image_mime, chat_id=chat_id,
                                user_id=user_id, platform="tg")
    user_imgs = [image_bytes] if image_bytes else None
    await _tg().send_tg_ai_response(message, chat_id, user_id, answer, user_text=prompt, user_images=user_imgs)
    asyncio.create_task(extract_memory(chat_key, f"{display_name}: [медиа] {caption}", answer,
                                       platform="tg", user_id=user_id, source_chat_id=chat_id))


# ============================================================
# TG TEXT HANDLER
# ============================================================
async def handle_tg_text(message: types.Message) -> None:
    if message.from_user is None:
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    is_dm = message.chat.type == 'private'
    text = message.text or ""
    tl = text.lower()
    display_name = message.from_user.full_name or "Unknown"
    username = message.from_user.username or ""
    chat_key = f"tg_{chat_id}"

    cfg = get_user_config("tg", chat_id, user_id)
    lang = cfg.get("language", "ru")

    if user_id in prompt_waiting:
        waiting_msg_id = prompt_waiting.pop(user_id, None)
        new_prompt = text.strip()
        if new_prompt.lower() in ("отмена", "cancel", "/cancel", "отменить"):
            cfg["custom_prompt"] = None
            save_user_configs()
            if waiting_msg_id:
                try:
                    await _tg().tg_bot.edit_message_text(tr(lang, "prompt_cancelled"), chat_id, waiting_msg_id)
                except Exception:
                    pass
        else:
            truncated = new_prompt[:2000]
            cfg["custom_prompt"] = truncated
            save_user_configs()
            if waiting_msg_id:
                try:
                    await _tg().tg_bot.edit_message_text(tr(lang, "prompt_saved", len(truncated)), chat_id, waiting_msg_id)
                except Exception:
                    pass
        return

    # Боты
    if message.from_user.is_bot:
        if not _is_addressed_from_bot_tg(message):
            return
        now = time.time()
        if now - last_bot_reply.get(chat_key, 0) < 8:
            return
        last_bot_reply[chat_key] = now

    if tl.startswith("кульш конфиг") or tl.startswith("кульш настройки") or tl.startswith("kulsh config"):
        await _tg().tg_handle_config(message)
        return

    if tl.strip() in ("кульш статус", "kulsh status", "кульш состояние"):
        await _tg().handle_status(message)
        return

    m = re.match(r'(?i)^(?:кульш\s+)?(?:поиск|search|найди|найти)\s+(.+)$', text.strip(), re.DOTALL)
    if m:
        await _tg().tg_handle_search(message, m.group(1).strip(), chat_id, user_id)
        return

    m = re.match(r'(?i)^(?:кульш\s+)?(?:график|chart|инфографика|диаграмма)\s+(.+)$', text.strip(), re.DOTALL)
    if m:
        await _tg().tg_handle_chart_request(message, m.group(1).strip(), chat_id, user_id)
        return

    if tl.startswith("кульш донаты") or tl.startswith("kulsh donations"):
        top = get_top_donators()
        if not top:
            await _tg().reply_tg_html(message, tr(lang, "top_donators_empty", DONATE_URL))
            return
        lines = [f"{tr(lang, 'top_donators_title')}\n"]
        for i, (name, total) in enumerate(top, 1):
            lines.append(tr(lang, "top_donators_item", i, html.escape(name), total))
        await _tg().send_formatted(chat_id, "\n".join(lines), reply_to=message.message_id)
        return

    if tl.startswith("кульш аватарк") or tl.startswith("кульш аватар") or tl.startswith("kulsh avatar") or tl.strip() in ("!avatar", "! avatar"):
        await _tg().tg_handle_avatar(message, chat_id, user_id)
        return

    if tl.startswith("кульш вспомни медиа") or tl.startswith("kulsh recall") or "!recall_media" in tl:
        await _tg().tg_handle_recall_media(message, chat_id, user_id, text.split())
        return

    if tl.startswith("кульш логи") or tl.startswith("kulsh logs"):
        if user_id != PREMIUM_ADMIN_ID:
            try:
                member = await _tg().tg_bot.get_chat_member(chat_id, user_id)
                if member.status not in ('administrator', 'creator'):
                    await _tg().reply_tg_html(message, tr(lang, "logs_no_access"))
                    return
            except Exception:
                await _tg().reply_tg_html(message, tr(lang, "logs_cant_check"))
                return
        try:
            tail = read_log_tail(20)
            full_caption = f"{LOG_INTRO}\n\n{tail}"
            if len(full_caption) <= 1024:
                caption, extra_text = full_caption, None
            else:
                available = 1024 - len(LOG_INTRO) - 5
                caption = f"{LOG_INTRO}\n\n{tail[:available]}..."
                extra_text = tail
            try:
                with open('bot.log', 'rb') as logf:
                    await _tg().tg_bot.send_document(chat_id, InputFile(logf), caption=caption)
            except FileNotFoundError:
                await _tg().send_tg_html(chat_id, full_caption[:4000], reply_to=message.message_id)
                return
            if extra_text:
                for chunk in chunk_text(extra_text, 3900):
                    try:
                        await _tg().tg_bot.send_message(chat_id, f"<pre>{html.escape(chunk)}</pre>", parse_mode='HTML')
                    except Exception:
                        await _tg().tg_bot.send_message(chat_id, chunk)
        except Exception as e:
            await _tg().reply_tg_html(message, tr(lang, "logs_read_error", str(e)))
        return

    if is_femboy_rate_command(text):
        user_femboy_state[chat_id] = True
        add_user_memory(chat_key, "TG", display_name, username, user_id, text, message_id=message.message_id)
        await _tg().reply_tg_html(message, tr(lang, "femboy_need_photo"))
        return

    if is_femboy_battle_command(text):
        add_user_memory(chat_key, "TG", display_name, username, user_id, text, message_id=message.message_id)
        await _tg().reply_tg_html(message, tr(lang, "femboy_battle_need_photos"))
        return

    if is_looksmaxxing_command(text):
        user_looksmaxxing_state[chat_id] = True
        add_user_memory(chat_key, "TG", display_name, username, user_id, text, message_id=message.message_id)
        await _tg().reply_tg_html(message, tr(lang, "psl_need_photo"))
        return

    if is_battle_command(text):
        add_user_memory(chat_key, "TG", display_name, username, user_id, text, message_id=message.message_id)
        await _tg().reply_tg_html(message, tr(lang, "battle_need_photos"))
        return

    is_reply_to_bot = (message.reply_to_message and message.reply_to_message.from_user
                       and message.reply_to_message.from_user.id == (tg_bot_id() or 0))
    addressed = bool(is_reply_to_bot or re.search(r'(?i)\bкульш\b', text) or is_dm)

    if addressed:
        try:
            await _tg().tg_bot.send_chat_action(chat_id, 'typing')
        except Exception:
            pass
        # Если это реплай на сообщение с медиа — добавляем в память msg_id родителя
        parent_media_id = None
        if message.reply_to_message and message.reply_to_message.message_id:
            from src.util import find_media_by_message_id
            if find_media_by_message_id(chat_key, message.reply_to_message.message_id):
                parent_media_id = message.reply_to_message.message_id
        text_for_memory = text
        if parent_media_id:
            text_for_memory = f"{text} [отвечает на msg_id:{parent_media_id} (медиа)]"
        add_user_memory(chat_key, "TG", display_name, username, user_id, text_for_memory,
                        message_id=message.message_id)
        messages = memory_to_messages(get_chat_memory(chat_key))
        answer = await ask_ai_async(messages=messages, chat_id=chat_id, user_id=user_id, platform="tg")
        await _tg().send_tg_ai_response(message, chat_id, user_id, answer, user_text=text)
        asyncio.create_task(extract_memory(chat_key, f"{display_name}: {text}", answer,
                                           platform="tg", user_id=user_id, source_chat_id=chat_id))
        asyncio.create_task(_tg().maybe_reply_to_old_message_tg(message, chat_id, user_id))
        return

    add_user_memory(chat_key, "TG", display_name, username, user_id, text, message_id=message.message_id)

    if await _tg().should_random_reply("tg", chat_id, user_id):
        try:
            answer = await ask_ai_async(
                context_type="observer",
                messages=memory_to_messages(get_chat_memory(chat_key)),
                chat_id=chat_id, user_id=user_id, platform="tg",
            )
            if answer and answer.strip() and answer.strip().upper() not in ("НЕТ", "NO"):
                last_random_reply[chat_key] = time.time()
                await _tg().send_tg_ai_response(message, chat_id, user_id, answer)
        except Exception as e:
            logger.warning(f"Random reply: {e}")


# ============================================================
# PSL BATTLE MEDIA GROUP
# ============================================================
async def process_battle_media_group(media_group_id: str, tg_chat_id: int, user_id: int) -> None:
    for _ in range(10):
        if media_group_id in battle_photos and len(battle_photos[media_group_id]) >= 2:
            break
        await asyncio.sleep(0.5)
    cfg = get_user_config("tg", tg_chat_id, user_id)
    lang = cfg.get("language", "ru")
    if media_group_id not in battle_photos or len(battle_photos[media_group_id]) < 2:
        battle_photos.pop(media_group_id, None)
        battle_media_groups.pop(media_group_id, None)
        await _tg().tg_bot.send_message(tg_chat_id, tr(lang, "battle_need_photos"))
        return
    photos = battle_photos.pop(media_group_id)
    battle_media_groups.pop(media_group_id, None)
    photo1_bytes, photo2_bytes = photos[:2]
    theme = cfg.get("theme", "dark")
    try:
        await _tg().tg_bot.send_chat_action(tg_chat_id, 'typing')
    except Exception:
        pass
    status = await _tg().tg_bot.send_message(tg_chat_id, tr(lang, "battle_waiting"))
    ai_data = await get_battle_data(photo1_bytes, photo2_bytes, lang=lang)
    if "error" in ai_data:
        await _tg().tg_bot.edit_message_text(ai_data['error'], tg_chat_id, status.message_id)
        return
    battle_img = await create_battle_infographic(photo1_bytes, photo2_bytes, ai_data, theme=theme, lang=lang)
    winner_num = str(ai_data.get("winner", "1"))
    winner_label = tr(lang, "battle_first") if winner_num == "1" else tr(lang, "battle_second")
    report_text = (
        f"<b>{tr(lang, 'battle_title')}</b>\n\n"
        f"{tr(lang, 'battle_winner')} <b>{winner_label}</b>\n"
        f"{tr(lang, 'battle_reason')} {html.escape(ai_data.get('reason', ''))}\n\n"
    )
    try:
        await _tg().tg_bot.send_photo(tg_chat_id, InputFile(battle_img), caption=tr(lang, "battle_caption"))
    except Exception as e:
        logger.error(f"battle infra: {e}")
    try:
        await _tg().tg_bot.send_message(tg_chat_id, report_text, parse_mode='HTML')
    except Exception:
        await _tg().tg_bot.send_message(tg_chat_id, re.sub(r'<[^>]+>', '', report_text))
    await _tg().tg_bot.delete_message(tg_chat_id, status.message_id)
