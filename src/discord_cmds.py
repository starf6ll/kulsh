# Kulsh GPT | v2.45.0
# by (main author): starfall-apk
# coauthor & bot hosting: pomidorka1515

"""Discord slash commands and channel-config helpers."""

import asyncio
import json
import random
import re
from typing import Any

import discord
from discord import app_commands

from src.ai import extract_search_marker, format_search_results, ask_ai_async, web_search, user_wants_chart
from src.charts import extract_chart_marker, render_infographic
from src.looks import (
    create_battle_infographic,
    create_femboy_battle_infographic,
    create_femboy_infographic,
    create_infographic,
    get_battle_data,
    get_femboy_battle_data,
    get_femboy_data,
    get_looksmaxxing_data,
)
from src.util import (
    BOT_VERSION,
    DAILY_CREDITS,
    DONATE_URL,
    GITHUB_URL,
    MINI_APP_URL,
    MODEL_DISPLAY,
    MODEL_LIST,
    RECALL_MEDIA_ID_PATTERN,
    add_bot_memory,
    as_member,
    calc_typing_delay,
    chat_media_history,
    clean_extra_text,
    clean_json_text,
    download_image_bytes,
    ds_user,
    extract_reaction_and_why,
    extract_video_frame,
    find_media_by_message_id,
    get_ds_scope,
    get_effective_config,
    get_user_credits,
    get_write_config,
    human_uptime,
    json_str,
    logger,
    model_display_name,
    premium_functions_enabled,
    process_ai_response,
    read_log_tail,
    save_user_configs,
    scrub_stray_markers,
    set_ds_scope,
    split_emojis,
    strip_chat_emojis,
    tr,
    AUTHORIZED_UPDATERS,
    GIF_POOL,
)

ds_bot: Any = None


def bind(bot: Any) -> None:
    global ds_bot
    ds_bot = bot


async def typing_with_delay_ds(channel: discord.abc.Messageable, text: str, delay: float | None = None) -> None:
    if delay is None:
        delay = calc_typing_delay(text)
    elapsed = 0.0
    chunk = 7.0
    while elapsed < delay:
        step = min(chunk, delay - elapsed)
        try:
            async with channel.typing():
                await asyncio.sleep(step)
        except Exception:
            await asyncio.sleep(step)
        elapsed += step


async def get_avatar_description_ds(message: discord.Message, chat_id: int, user_id: int, lang: str = "ru") -> str | None:
    target = None
    me = ds_user(ds_bot)
    if message.mentions:
        for m in message.mentions:
            if m.id != me.id:
                target = m
                break
    if target is None and message.reference and message.reference.resolved and isinstance(message.reference.resolved, discord.Message):
        ref_auth = message.reference.resolved.author
        if ref_auth.id != me.id:
            target = ref_auth
    if target is None and message.author.id != me.id:
        target = message.author
    if target is None:
        return None
    name = target.display_name
    try:
        img_bytes = await download_image_bytes(target.display_avatar.url)
        prompt = (
            f"Ты только что посмотрел аватарку пользователя {name}. "
            f"Опиши коротко (1-2 предложения) в стиле Кульша. Без markdown. "
            f"Без маркеров."
            if lang == "ru" else
            f"You've just seen the avatar of {name}. Describe briefly. No markers."
        )
        desc = json_str(await ask_ai_async(
            prompt=prompt, image_bytes=img_bytes, image_mime="image/jpeg",
            chat_id=chat_id, user_id=user_id, platform="ds",
        ))
        return desc or None
    except Exception as e:
        logger.warning(f"DS avatar desc: {e}")
        return None


async def execute_utility_ds(message: discord.Message, marker: str, chat_id: int, user_id: int) -> None:
    cfg = get_effective_config("ds", chat_id, user_id)
    if marker in ("sticker", "gif"):
        if not cfg.get("stickers_enabled", True):
            return
        try:
            gif_url = random.choice(GIF_POOL)
            embed = discord.Embed().set_image(url=gif_url)
            await message.reply(embed=embed)
        except Exception as e:
            logger.error(f"gif error: {e}")


def _ds_bot_user() -> discord.ClientUser | None:
    try:
        return ds_bot.user if ds_bot else None
    except Exception:
        return None


async def fetch_last_media_ds(chat_id: int) -> tuple[bytes | None, str, int | None]:
    history = list(chat_media_history.get(f"ds_{chat_id}", []))
    if not history:
        return None, "", None
    for item in reversed(history):
        url = item.get("url")
        mtype = str(item.get("type") or "")
        mid = item.get("message_id")
        if not url:
            continue
        try:
            if mtype == "photo":
                b = await download_image_bytes(url)
                if b:
                    return b, "photo", mid
            elif mtype in ("video", "animation"):
                raw = await download_image_bytes(url)
                frame = await extract_video_frame(raw, ".mp4")
                if frame:
                    return frame, mtype, mid
        except Exception as e:
            logger.warning(f"fetch_last_media_ds ({mtype}): {e}")
            continue
    return None, "", None


async def fetch_media_by_id_ds(chat_id: int, message_id: int) -> tuple[bytes | None, str]:
    item = find_media_by_message_id(f"ds_{chat_id}", message_id)
    if not item:
        return None, ""
    url = item.get("url")
    mtype = str(item.get("type") or "")
    if not url:
        return None, ""
    try:
        if mtype == "photo":
            b = await download_image_bytes(url)
            return (b, "photo") if b else (None, "")
        elif mtype in ("video", "animation"):
            raw = await download_image_bytes(url)
            frame = await extract_video_frame(raw, ".mp4")
            return (frame, mtype) if frame else (None, "")
    except Exception as e:
        logger.warning(f"fetch_media_by_id_ds: {e}")
    return None, ""


async def send_ds_ai_response(message: discord.Message, chat_id: int, user_id: int,
                              answer_raw: str, user_text: str | None = None) -> None:
    cfg = get_effective_config("ds", chat_id, user_id)
    lang = cfg.get("language", "ru")
    separate_enabled = cfg.get("separate_enabled", True)
    orig_user_text = (user_text or message.content or "").strip()

    # ---- react / why ----
    applied_reactions: list[str] = []
    if cfg.get("reactions_enabled", True):
        cleaned_text, emojis_str, why_text = extract_reaction_and_why(answer_raw or "")
        if emojis_str:
            reply_target: discord.Message | None = None
            if message.reference and message.reference.resolved and isinstance(message.reference.resolved, discord.Message):
                reply_target = message.reference.resolved
            me = _ds_bot_user()
            target_from_bot = False
            if reply_target is not None and me is not None and reply_target.author == me:
                target_from_bot = True
            if reply_target is None and me is not None and message.author == me:
                target_from_bot = True
            if not target_from_bot:
                emojis = split_emojis(emojis_str)
                for e in emojis[:3]:
                    try:
                        target = reply_target or message
                        await target.add_reaction(e)
                        applied_reactions.append(e)
                    except Exception as ex:
                        logger.warning(f"add_reaction {e}: {ex}")
                if applied_reactions and why_text:
                    add_bot_memory(f"ds_{chat_id}", f"[реакция {' '.join(applied_reactions)}] {why_text}")
                elif applied_reactions:
                    add_bot_memory(f"ds_{chat_id}", f"[реакция {' '.join(applied_reactions)}]")
        answer_raw = cleaned_text

    # ---- search ----
    if cfg.get("web_search_enabled", True):
        query, _ = extract_search_marker(answer_raw or "")
        if query:
            results = await web_search(query, max_results=6)
            if results:
                context = format_search_results(results)
                follow_prompt = (
                    f"Пользователь спросил: {orig_user_text}\n\n"
                    f"Ты выполнил поиск: {query}\n\nРезультаты:\n{context}\n\n"
                    f"Ответь кратко. Без !search, !chart."
                )
                answer_raw = await ask_ai_async(prompt=follow_prompt, chat_id=chat_id, user_id=user_id, platform="ds")
            else:
                answer_raw = tr(lang, "search_nothing")

    # ---- !recall_media (с ID и без) ----
    rm_id: int | None = None
    rm_match = RECALL_MEDIA_ID_PATTERN.search(answer_raw or "")
    if rm_match:
        try:
            rm_id = int(rm_match.group(1))
        except ValueError:
            rm_id = None
    has_recall = bool(re.search(r'!\s*recall[\s_]*media(?![A-Za-z])', answer_raw or "", re.IGNORECASE))
    if has_recall or rm_id is not None:
        media_bytes: bytes | None = None
        media_kind: str = ""
        try:
            if rm_id is not None:
                media_bytes, media_kind = await fetch_media_by_id_ds(chat_id, rm_id)
            else:
                # Сначала пробуем медиа, на которое ответил пользователь
                if message.reference and message.reference.resolved and isinstance(message.reference.resolved, discord.Message):
                    parent_id = message.reference.resolved.id
                    media_bytes, media_kind = await fetch_media_by_id_ds(chat_id, parent_id)
                if media_bytes is None:
                    media_bytes, media_kind, _ = await fetch_last_media_ds(chat_id)
        except Exception as e:
            logger.warning(f"DS recall fetch: {e}")
            media_bytes, media_kind = None, ""

        if media_bytes:
            kind_label = {"photo": "фото", "video": "видео", "animation": "гифку"}.get(media_kind, "медиа")
            follow_prompt = (
                f"Пользователь написал: {orig_user_text or 'покажи последнее медиа'}\n\n"
                f"Вот медиа из чата — это {kind_label}. Опиши коротко и живо, что на нём, "
                f"в стиле Кульша. Маленькими буквами. Без маркеров."
            )
            new_answer = await ask_ai_async(
                prompt=follow_prompt, image_bytes=media_bytes, image_mime="image/jpeg",
                chat_id=chat_id, user_id=user_id, platform="ds",
            )
            if new_answer and new_answer.strip():
                answer_raw = new_answer
            else:
                answer_raw = tr(lang, "recall_fail")
        else:
            answer_raw = tr(lang, "recall_fail")
        # чистим ID-маркер, если остался
        answer_raw = RECALL_MEDIA_ID_PATTERN.sub(' ', answer_raw)
        answer_raw = re.sub(r'!\s*recall[\s_]*media', ' ', answer_raw, flags=re.IGNORECASE)

    # ---- chart ----
    if premium_functions_enabled:
        chart_spec, remaining = extract_chart_marker(answer_raw or "")
        if chart_spec:
            user_asked_chart = user_wants_chart(orig_user_text)
            if user_asked_chart:
                try:
                    img = await render_infographic(chart_spec, user_images=None)
                    try:
                        await message.reply(file=discord.File(fp=img, filename="infographic.png"),
                                            content=(chart_spec.get("title") or tr(lang, "chart_built"))[:1900])
                    except Exception as e:
                        logger.error(f"ds chart send: {e}")
                except Exception as e:
                    logger.error(f"ds chart render: {e}")
                    answer_raw = remaining + "\n" + tr(lang, "chart_error", str(e))
                    chart_spec = None
            if chart_spec is not None or not user_asked_chart:
                answer_raw = remaining

    clean_segments, markers = process_ai_response(answer_raw, separate_enabled=separate_enabled)

    extra_segments: list[str] = []
    if "avatar" in markers:
        markers.remove("avatar")
        try:
            ar = await get_avatar_description_ds(message, chat_id, user_id, lang=lang)
            if ar:
                extra_segments.extend(clean_extra_text(ar))
        except Exception as e:
            logger.warning(f"DS avatar: {e}")
    if "recall_media" in markers:
        markers.remove("recall_media")

    all_segments = clean_segments + extra_segments
    if not all_segments:
        for m in markers:
            if m in ("sticker", "gif"):
                try:
                    await execute_utility_ds(message, m, chat_id, user_id)
                except Exception as e:
                    logger.warning(f"ds utility: {e}")
        return

    for i, seg in enumerate(all_segments):
        seg = scrub_stray_markers(seg)
        if cfg.get("communication_mode", "kent") == "kent":
            seg = strip_chat_emojis(seg)
        if not seg:
            continue
        try:
            await typing_with_delay_ds(message.channel, seg, delay=calc_typing_delay(seg, segment_index=i))
        except Exception:
            pass
        if i == 0:
            try:
                await message.reply(seg)
            except Exception:
                await message.channel.send(seg)
        else:
            await message.channel.send(seg)
        add_bot_memory(f"ds_{chat_id}", seg)

    for m in markers:
        if m in ("sticker", "gif"):
            try:
                await execute_utility_ds(message, m, chat_id, user_id)
            except Exception as e:
                logger.warning(f"ds utility {m}: {e}")


# ============================================================
# CONFIG
# ============================================================
def ds_config_embed(chat_id: int, user_id: int) -> discord.Embed:
    scope = get_ds_scope(chat_id)
    cfg = get_effective_config("ds", chat_id, user_id)
    lang = cfg.get("language", "ru")
    series = tr(lang, "on") if cfg.get("series_reminder_enabled", True) else tr(lang, "off")
    stickers = tr(lang, "on") if cfg.get("stickers_enabled", True) else tr(lang, "off")
    sep = tr(lang, "on") if cfg.get("separate_enabled", True) else tr(lang, "off")
    autoreply = tr(lang, "on") if cfg.get("random_reply_enabled", False) else tr(lang, "off")
    random_msgs = tr(lang, "on") if cfg.get("random_messages_enabled", True) else tr(lang, "off")
    websearch = tr(lang, "on") if cfg.get("web_search_enabled", True) else tr(lang, "off")
    reactions = tr(lang, "on") if cfg.get("reactions_enabled", True) else tr(lang, "off")
    prompt = cfg.get("custom_prompt") or ("стандартный" if lang == "ru" else "default")
    if len(prompt) > 900:
        prompt = prompt[:900] + "..."
    theme_disp = tr(lang, "dark") if cfg.get("theme", "dark") == "dark" else tr(lang, "light")
    lang_disp = tr(lang, "russian") if lang == "ru" else tr(lang, "english")
    mode_raw = str(cfg.get("communication_mode", "kent"))
    mode_disp = tr(lang, "mode_assistant") if mode_raw == "assistant" else (tr(lang, "mode_pro") if mode_raw == "pro" else tr(lang, "mode_kent"))

    if scope == "shared":
        scope_disp = "🌐 Общие для канала (админ)" if lang == "ru" else "🌐 Shared for channel (admin)"
    else:
        scope_disp = "👤 Личные для каждого" if lang == "ru" else "👤 Per-user"

    title = "✦ Настройки Кульша ✦" if lang == "ru" else "✦ Kulsh Settings ✦"
    desc = ("Область настроек: админ может задать общий набор для канала или разрешить каждому свои."
            if lang == "ru" else
            "Config scope: admin can set shared for the channel or allow per-user.")
    embed = discord.Embed(title=title, color=0x10B981, description=desc)

    if lang == "ru":
        embed.add_field(name="🎛 Область", value=scope_disp, inline=False)
        embed.add_field(name="🌐 Язык", value=lang_disp, inline=True)
        embed.add_field(name="🌓 Тема", value=theme_disp, inline=True)
        embed.add_field(name="🧩 Режим", value=mode_disp, inline=True)
        embed.add_field(name="🧠 Модель", value=model_display_name(cfg.get("model"), lang), inline=True)
        embed.add_field(name="🎛 Температура", value=str(cfg.get("temperature", 0.9)), inline=True)
        embed.add_field(name="💬 Разбивка", value=sep, inline=True)
        embed.add_field(name="😀 Реакции", value=reactions, inline=True)
        embed.add_field(name="🎨 Стикеры/гифки", value=stickers, inline=True)
        embed.add_field(name="🗣 Автоответ", value=autoreply, inline=True)
        embed.add_field(name="📢 Случайные", value=random_msgs, inline=True)
        embed.add_field(name="🔎 Веб-поиск", value=websearch, inline=True)
        embed.add_field(name="🎬 Серия", value=series, inline=True)
        embed.add_field(name="📝 Кастомный промпт", value=prompt, inline=False)
        embed.add_field(
            name="📖 Команды",
            value=(
                "`кульш конфиг область для_себя|для_всех`\n"
                "`кульш конфиг язык ru|en`\n"
                "`кульш конфиг тема тёмная|светлая`\n"
                "`кульш конфиг режим кент|ассистент`\n"
                "`кульш конфиг модель <номер|авто>`\n"
                "`кульш конфиг температура <0.0-2.0>`\n"
                "`кульш конфиг разбивка вкл|выкл`\n"
                "`кульш конфиг реакции вкл|выкл`\n"
                "`кульш конфиг стикеры вкл|выкл`\n"
                "`кульш конфиг автоответ вкл|выкл`\n"
                "`кульш конфиг рандом вкл|выкл`\n"
                "`кульш конфиг поиск вкл|выкл`\n"
                "`кульш конфиг промпт <текст|сброс>`"
            ),
            inline=False,
        )
    else:
        embed.add_field(name="🎛 Scope", value=scope_disp, inline=False)
        embed.add_field(name="🌐 Language", value=lang_disp, inline=True)
        embed.add_field(name="🌓 Theme", value=theme_disp, inline=True)
        embed.add_field(name="🧩 Mode", value=mode_disp, inline=True)
        embed.add_field(name="🧠 Model", value=model_display_name(cfg.get("model"), lang), inline=True)
        embed.add_field(name="🎛 Temperature", value=str(cfg.get("temperature", 0.9)), inline=True)
        embed.add_field(name="💬 Split", value=sep, inline=True)
        embed.add_field(name="😀 Reactions", value=reactions, inline=True)
        embed.add_field(name="🎨 Stickers/GIFs", value=stickers, inline=True)
        embed.add_field(name="🗣 Auto-reply", value=autoreply, inline=True)
        embed.add_field(name="📢 Random", value=random_msgs, inline=True)
        embed.add_field(name="🔎 Web search", value=websearch, inline=True)
        embed.add_field(name="🎬 Series", value=series, inline=True)
        embed.add_field(name="📝 Custom prompt", value=prompt, inline=False)
    return embed


async def ds_handle_config(message: discord.Message, user_id: int) -> None:
    chat_id = message.channel.id
    member = as_member(message.author)
    is_admin = bool(member and member.guild_permissions.administrator) if message.guild else True
    scope = get_ds_scope(chat_id)
    if scope == "shared" and not is_admin:
        # не админ в shared-режиме — показываем только его личные (self) значения
        embed = ds_config_embed(chat_id, user_id)
        await message.reply(embed=embed)
        return
    embed = ds_config_embed(chat_id, user_id)
    await message.reply(embed=embed)


async def ds_handle_config_param(message: discord.Message, user_id: int, parts: list[str]) -> None:
    chat_id = message.channel.id
    scope = get_ds_scope(chat_id)
    cfg_read = get_effective_config("ds", chat_id, user_id)
    lang = cfg_read.get("language", "ru")
    member = as_member(message.author)
    is_admin = bool(member and member.guild_permissions.administrator) if message.guild else True
    # В shared-режиме менять может только админ; в self — каждый свои.
    if scope == "shared" and not is_admin:
        await message.reply(
            "в этом канале настройки общие и меняет только админ" if lang == "ru" else
            "shared config in this channel, only admin can change"
        )
        return
    if len(parts) < 3:
        await ds_handle_config(message, user_id)
        return
    param = parts[2].lower()
    val = parts[3].lower() if len(parts) >= 4 else ""
    bool_on = val in ("вкл", "on", "1", "true", "да", "yes")

    # Запись всегда в правильный конфиг
    cfg = get_write_config("ds", chat_id, user_id)

    if param in ("область", "scope"):
        if not is_admin:
            await message.reply("только админ может менять область настроек")
            return
        if val in ("для_себя", "для-себя", "self", "личные", "личная"):
            set_ds_scope(chat_id, "self")
            await message.reply("👤 Область: личные настройки для каждого")
        elif val in ("для_всех", "для-всех", "shared", "общие", "общая"):
            set_ds_scope(chat_id, "shared")
            await message.reply("🌐 Область: общие настройки для всего канала (задаёт админ)")
        else:
            await message.reply("укажи `для_себя` или `для_всех`")
    elif param in ("язык", "language"):
        if val in ("ru", "русский", "russian"):
            cfg["language"] = "ru"; save_user_configs()
            await message.reply(tr("ru", "ds_setting_lang", tr("ru", "russian")))
        elif val in ("en", "английский", "english"):
            cfg["language"] = "en"; save_user_configs()
            await message.reply(tr("en", "ds_setting_lang", tr("en", "english")))
        else:
            await message.reply(tr(lang, "ds_need_specify_ru_en"))
    elif param in ("тема", "theme"):
        if val in ("тёмная", "темная", "dark"):
            cfg["theme"] = "dark"; save_user_configs()
            await message.reply(tr(lang, "ds_setting_theme", tr(lang, "dark")))
        elif val in ("светлая", "light"):
            cfg["theme"] = "light"; save_user_configs()
            await message.reply(tr(lang, "ds_setting_theme", tr(lang, "light")))
        else:
            await message.reply(tr(lang, "ds_need_specify_theme"))
    elif param in ("режим", "mode"):
        if val in ("кент", "kent", "default"):
            cfg["communication_mode"] = "kent"; save_user_configs()
            await message.reply(tr(lang, "ds_setting_mode", tr(lang, "mode_kent")))
        elif val in ("ассистент", "assistant"):
            cfg["communication_mode"] = "assistant"; save_user_configs()
            await message.reply(tr(lang, "ds_setting_mode", tr(lang, "mode_assistant")))
        elif val == "pro":
            await message.reply(tr(lang, "mode_need_dm"))
        else:
            await message.reply(tr(lang, "ds_unknown_param"))
    elif param in ("серия", "series"):
        cfg["series_reminder_enabled"] = bool_on; save_user_configs()
        await message.reply(tr(lang, "ds_setting_series", tr(lang, "on") if bool_on else tr(lang, "off")))
    elif param in ("стикеры", "stickers"):
        cfg["stickers_enabled"] = bool_on; save_user_configs()
        await message.reply(tr(lang, "ds_setting_stickers", tr(lang, "on") if bool_on else tr(lang, "off")))
    elif param in ("разбивка", "split"):
        cfg["separate_enabled"] = bool_on; save_user_configs()
        await message.reply(tr(lang, "ds_setting_sep", tr(lang, "on") if bool_on else tr(lang, "off")))
    elif param in ("реакции", "reactions"):
        cfg["reactions_enabled"] = bool_on; save_user_configs()
        await message.reply(tr(lang, "ds_setting_reactions", tr(lang, "on") if bool_on else tr(lang, "off")))
    elif param in ("автоответ", "autoreply"):
        cfg["random_reply_enabled"] = bool_on; save_user_configs()
        await message.reply(tr(lang, "ds_setting_autoreply", tr(lang, "on") if bool_on else tr(lang, "off")))
    elif param in ("рандом", "random"):
        cfg["random_messages_enabled"] = bool_on; save_user_configs()
        await message.reply(tr(lang, "ds_setting_random", tr(lang, "on") if bool_on else tr(lang, "off")))
    elif param in ("поиск", "search"):
        cfg["web_search_enabled"] = bool_on; save_user_configs()
        await message.reply(tr(lang, "ds_setting_websearch", tr(lang, "on") if bool_on else tr(lang, "off")))
    elif param in ("температура", "temperature"):
        try:
            t = max(0.0, min(2.0, float(val)))
            cfg["temperature"] = t; save_user_configs()
            await message.reply(tr(lang, "ds_setting_temp", t))
        except ValueError:
            await message.reply(tr(lang, "ds_setting_temp_bad"))
    elif param in ("промпт", "prompt"):
        new_prompt = " ".join(parts[3:]).strip()
        if new_prompt.lower() in ("сброс", "reset", "убрать", "стандарт", "default"):
            cfg["custom_prompt"] = None; save_user_configs()
            await message.reply(tr(lang, "ds_setting_prompt_reset"))
        elif new_prompt:
            cfg["custom_prompt"] = new_prompt[:2000]; save_user_configs()
            await message.reply(tr(lang, "ds_setting_prompt_set"))
        else:
            await message.reply(tr(lang, "ds_setting_prompt_need"))
    elif param in ("модель", "model"):
        if not val:
            lines = [f"`{i}` — {MODEL_DISPLAY.get(m, m)}" for i, m in enumerate(MODEL_LIST)]
            await message.reply(f"{tr(lang, 'ds_setting_model', model_display_name(cfg.get('model'), lang))}\n\n" + "\n".join(lines))
        elif val in ("авто", "auto"):
            cfg["model"] = None; save_user_configs()
            await message.reply(tr(lang, "ds_setting_model_auto"))
        else:
            try:
                idx = int(val)
                if 0 <= idx < len(MODEL_LIST):
                    cfg["model"] = MODEL_LIST[idx]; save_user_configs()
                    await message.reply(tr(lang, "ds_setting_model", MODEL_DISPLAY.get(MODEL_LIST[idx], MODEL_LIST[idx])))
                else:
                    await message.reply(tr(lang, "ds_setting_model_badnum"))
            except ValueError:
                await message.reply(tr(lang, "ds_setting_model_bad"))
    else:
        await message.reply(tr(lang, "ds_unknown_param"))


def ds_help_text(lang: str) -> str:
    return tr(lang, "help_body", MINI_APP_URL, GITHUB_URL)


def ds_menu_text(lang: str) -> str:
    if lang == "ru":
        return (
            "# ✦ Кульш AI — меню ✦\n\n---\n\n"
            "Открытая языковая модель с набором инструментов.\n\n"
            "**Основные**\n\n- `/start` — приветствие\n- `/help` — полный список команд\n"
            "- `/status` — состояние бота\n- `/config` — настройки канала\n"
            "- `/donate` — поддержка\n- `/credits` — кредиты\n\n"
            "**Инструменты**\n\n- `/avatar` — аватарка\n- `/recall` — последние медиа\n"
            "- `/search` — веб-поиск\n- `/chart` — инфографика\n"
            "- `/psl` — оценка внешности\n- `/battle` — баттл фото\n"
            "- `/femboy` — Femboy Rate\n- `/femboy-battle` — фембой-баттл\n"
            "- `/groupinfo` — инфо о сервере\n- `/userinfo` — инфо о пользователе\n"
            "- `/logs` — логи (админам)\n\n"
            f"🍷🗿 {MINI_APP_URL}"
        )
    return (
        "# ✦ Kulsh AI — menu ✦\n\n---\n\n"
        "An open-source language model with built-in tools.\n\n"
        f"🍷🗿 {MINI_APP_URL}"
    )


def ds_start_text(lang: str) -> str:
    if lang == "ru":
        return (
            "# 🍷🗿 Кульш на связи\n\n---\n\n"
            "Открытая языковая модель с анализом изображений.\n\n"
            "**🚀 С чего начать**\n\n- `/menu` — все разделы\n- `/help` — команды\n"
            "- `/status` — состояние\n- `/config` — настройки\n\n"
            f"🍷🗿 {MINI_APP_URL}"
        )
    return (
        "# 🍷🗿 Kulsh is online\n\n---\n\n"
        "An open-source language model with image analysis.\n\n"
        f"🍷🗿 {MINI_APP_URL}"
    )


def ds_lang_of(interaction: discord.Interaction) -> str:
    chat_id = interaction.channel_id or 0
    user_id = interaction.user.id
    cfg = get_effective_config("ds", chat_id, user_id)
    lang = cfg.get("language", "ru")
    return lang if isinstance(lang, str) else "ru"


async def ds_slash_start(interaction: discord.Interaction) -> None:
    lang = ds_lang_of(interaction)
    await interaction.response.send_message(ds_start_text(lang))


async def ds_slash_menu(interaction: discord.Interaction) -> None:
    lang = ds_lang_of(interaction)
    await interaction.response.send_message(ds_menu_text(lang))


async def ds_slash_help(interaction: discord.Interaction) -> None:
    lang = ds_lang_of(interaction)
    await interaction.response.send_message(ds_help_text(lang))


async def ds_slash_status(interaction: discord.Interaction) -> None:
    lang = ds_lang_of(interaction)
    cfg = get_effective_config("ds", interaction.channel_id or 0, interaction.user.id)
    mode_raw = str(cfg.get("communication_mode", "kent"))
    mode_label = tr(lang, "mode_assistant") if mode_raw == "assistant" else (tr(lang, "mode_pro") if mode_raw == "pro" else tr(lang, "mode_kent"))
    try:
        latency_ms = round(interaction.client.latency * 1000)
    except Exception:
        latency_ms = 50
    text = (
        f"# 🟢 {tr(lang, 'status_title')}\n\n---\n\n"
        f"**{tr(lang, 'status_online')}**\n\n"
        f"- {tr(lang, 'status_uptime')}: `{human_uptime()}`\n"
        f"- {tr(lang, 'status_latency')}: `~{latency_ms} ms`\n"
        f"- {tr(lang, 'status_mode')}: `{mode_label}`\n"
        f"- {tr(lang, 'status_mood')}: `{tr(lang, 'status_mood_value')}`\n\n"
        f"🍷🗿 · v{BOT_VERSION}"
    )
    await interaction.response.send_message(text)


async def ds_slash_donate(interaction: discord.Interaction) -> None:
    lang = ds_lang_of(interaction)
    text = (
        f"# {tr(lang, 'donate_title')}\n\n---\n\n"
        f"{tr(lang, 'donate_intro')}\n\n"
        f"- {tr(lang, 'donate_online')}: {DONATE_URL}\n- 🔗 GitHub: {GITHUB_URL}"
    )
    await interaction.response.send_message(text)


async def ds_slash_credits(interaction: discord.Interaction) -> None:
    lang = ds_lang_of(interaction)
    creds = get_user_credits("ds", interaction.user.id)
    await interaction.response.send_message(tr(lang, "credits_balance", creds, DAILY_CREDITS))


@app_commands.describe(scope="Config scope (admin only) / Область (только админ)")
async def ds_slash_config(interaction: discord.Interaction, scope: str | None = None) -> None:
    chat_id = interaction.channel_id or 0
    user_id = interaction.user.id
    lang = ds_lang_of(interaction)
    member = as_member(interaction.user)
    is_admin = True
    if interaction.guild:
        is_admin = bool(member and member.guild_permissions.administrator)

    if scope:
        if not is_admin:
            await interaction.response.send_message(tr(lang, "ds_only_admins"), ephemeral=True)
            return
        s = scope.lower().strip()
        if s in ("self", "для_себя", "для-себя", "личные"):
            set_ds_scope(chat_id, "self")
            await interaction.response.send_message("👤 Область: личные для каждого" if lang == "ru" else "👤 Scope: per-user")
            return
        if s in ("shared", "для_всех", "для-всех", "общие"):
            set_ds_scope(chat_id, "shared")
            await interaction.response.send_message("🌐 Область: общие для канала (задаёт админ)" if lang == "ru" else "🌐 Scope: shared")
            return
        await interaction.response.send_message("укажи self или shared", ephemeral=True)
        return

    cur_scope = get_ds_scope(chat_id)
    if cur_scope == "shared" and not is_admin:
        # не админ — показываем только его собственные настройки (он их видит, но не может менять)
        embed = ds_config_embed(chat_id, user_id)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    embed = ds_config_embed(chat_id, user_id)
    await interaction.response.send_message(embed=embed, ephemeral=not is_admin)


@app_commands.describe(user="Whose avatar to describe / Чью аватарку описать")
async def ds_slash_avatar(interaction: discord.Interaction, user: discord.Member | None = None) -> None:
    await interaction.response.defer()
    target = user or interaction.user
    chat_id = interaction.channel_id or 0
    user_id = interaction.user.id
    lang = ds_lang_of(interaction)
    try:
        img_bytes = await download_image_bytes(target.display_avatar.url)
        prompt = (
            f"Ты только что посмотрел аватарку пользователя {target.display_name}. "
            f"Опиши коротко (1-2 предложения) в стиле Кульша. Без markdown."
            if lang == "ru" else
            f"You've just seen the avatar of {target.display_name}. Describe briefly."
        )
        raw = await ask_ai_async(prompt=prompt, image_bytes=img_bytes, image_mime="image/jpeg",
                                 chat_id=chat_id, user_id=user_id, platform="ds")
        segments = clean_extra_text(raw) if raw else []
        if not segments:
            await interaction.followup.send(tr(lang, "avatar_fail"))
            return
        for seg in segments:
            seg = scrub_stray_markers(seg)
            if seg:
                await interaction.followup.send(seg)
    except Exception as e:
        logger.error(f"DS slash avatar: {e}")
        await interaction.followup.send(f"Ошибка: {e}")


@app_commands.describe(count="How many last items / Сколько последних элементов")
async def ds_slash_recall(interaction: discord.Interaction, count: int = 3) -> None:
    await interaction.response.defer()
    chat_id = interaction.channel_id or 0
    user_id = interaction.user.id
    lang = ds_lang_of(interaction)
    _n = max(1, min(10, count))
    media_bytes, media_kind, _ = await fetch_last_media_ds(chat_id)
    if media_bytes is None:
        await interaction.followup.send(tr(lang, "recall_fail"))
        return
    kind_label = {"photo": "фото", "video": "видео", "animation": "гифку"}.get(media_kind, "медиа")
    prompt = (
        f"Вот последнее медиа в чате — это {kind_label}. Опиши коротко и живо, что на нём, "
        f"в стиле Кульша. Без маркеров."
    )
    raw = await ask_ai_async(prompt=prompt, image_bytes=media_bytes, image_mime="image/jpeg",
                             chat_id=chat_id, user_id=user_id, platform="ds")
    if raw and raw.strip():
        for seg in clean_extra_text(raw):
            seg = scrub_stray_markers(seg)
            if seg:
                await interaction.followup.send(seg)
    else:
        await interaction.followup.send(tr(lang, "recall_fail"))


async def ds_slash_logs(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    lang = ds_lang_of(interaction)
    if interaction.user.id not in AUTHORIZED_UPDATERS:
        await interaction.followup.send(tr(lang, "ds_update_no_access"), ephemeral=True)
        return
    try:
        tail = read_log_tail(20)
        intro = tr(lang, "ds_logs_content")
        content = f"{intro}\n```\n{tail}\n```" if len(tail) <= 1900 else f"{intro}\n\n{tail[:1900]}"
        try:
            await interaction.followup.send(content=content, file=discord.File('bot.log'), ephemeral=True)
        except FileNotFoundError:
            await interaction.followup.send(content=content, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Ошибка: {e}", ephemeral=True)


@app_commands.describe(query="What to search / Что искать")
async def ds_slash_search(interaction: discord.Interaction, query: str) -> None:
    await interaction.response.defer()
    chat_id = interaction.channel_id or 0
    user_id = interaction.user.id
    lang = ds_lang_of(interaction)
    cfg = get_effective_config("ds", chat_id, user_id)
    if not cfg.get("web_search_enabled", True):
        await interaction.followup.send(tr(lang, "search_off"))
        return
    results = await web_search(query, max_results=6)
    if not results:
        await interaction.followup.send(tr(lang, "search_nothing"))
        return
    context = format_search_results(results)
    prompt = (
        f"Пользователь искал: {query}\n\n{context}\n\nКраткий ответ в стиле Кульша. Без !search, !chart."
    )
    answer = await ask_ai_async(prompt=prompt, chat_id=chat_id, user_id=user_id, platform="ds")
    full = f"🔎 **{query}**\n\n{answer or ''}"
    await interaction.followup.send(full[:1900])


@app_commands.describe(description="Describe the chart / Опиши график")
async def ds_slash_chart(interaction: discord.Interaction, description: str) -> None:
    await interaction.response.defer()
    chat_id = interaction.channel_id or 0
    user_id = interaction.user.id
    lang = ds_lang_of(interaction)
    chart_prompt = (
        f"Сгенерируй JSON-спецификацию инфографики по описанию:\n\n{description}\n\n"
        f"Верни ТОЛЬКО JSON-объект без markdown."
    )
    raw = await ask_ai_async(
        prompt=chart_prompt,
        system_instruction_override="You are a data-visualization JSON generator. Output ONLY valid JSON.",
        chat_id=chat_id, user_id=user_id, platform="ds",
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
        await interaction.followup.send(tr(lang, "chart_error", "invalid JSON"))
        return
    try:
        img = await render_infographic(spec, user_images=None)
    except Exception as e:
        await interaction.followup.send(tr(lang, "chart_error", str(e)))
        return
    try:
        await interaction.followup.send(
            content=(spec.get("title") or tr(lang, "chart_built"))[:1900],
            file=discord.File(fp=img, filename="infographic.png"),
        )
    except Exception as e:
        await interaction.followup.send(f"Ошибка отправки: {e}")


@app_commands.describe(image="Photo / Фото", advice="Include advice / Показать рекомендации")
async def ds_slash_psl(interaction: discord.Interaction, image: discord.Attachment, advice: bool = False) -> None:
    await interaction.response.defer()
    chat_id = interaction.channel_id or 0
    user_id = interaction.user.id
    lang = ds_lang_of(interaction)
    try:
        img_bytes = await download_image_bytes(image.url)
        cfg = get_effective_config("ds", chat_id, user_id)
        theme = cfg.get("theme", "dark")
        ai_data = await get_looksmaxxing_data(
            img_bytes, advice, lang=lang, chat_id=chat_id, user_id=user_id, platform="ds",
        )
        if ai_data.get("not_a_face"):
            await interaction.followup.send(ai_data.get("message", tr(lang, "psl_not_a_face")))
            return
        if "error" in ai_data:
            await interaction.followup.send(ai_data['error'])
            return
        infographic = await create_infographic(img_bytes, ai_data, theme=theme, lang=lang)
        report = (
            f"**{tr(lang, 'psl_title')}**\n"
            f"{tr(lang, 'psl_gender')} {ai_data.get('gender', '?')}\n"
            f"{tr(lang, 'psl_score')} `{ai_data.get('psl', '?')}/8.0`"
        )
        await interaction.followup.send(content=report[:1900],
                                        file=discord.File(fp=infographic, filename="psl.png"))
    except Exception as e:
        logger.error(f"DS slash psl: {e}")
        await interaction.followup.send(f"Ошибка: {e}")


@app_commands.describe(image1="First photo / Первое фото", image2="Second photo / Второе фото")
async def ds_slash_battle(interaction: discord.Interaction, image1: discord.Attachment, image2: discord.Attachment) -> None:
    await interaction.response.defer()
    chat_id = interaction.channel_id or 0
    user_id = interaction.user.id
    lang = ds_lang_of(interaction)
    try:
        p1 = await download_image_bytes(image1.url)
        p2 = await download_image_bytes(image2.url)
        cfg = get_effective_config("ds", chat_id, user_id)
        theme = cfg.get("theme", "dark")
        ai_data = await get_battle_data(p1, p2, lang=lang)
        if "error" in ai_data:
            await interaction.followup.send(ai_data['error'])
            return
        img = await create_battle_infographic(p1, p2, ai_data, theme=theme, lang=lang)
        winner_num = str(ai_data.get("winner", "1"))
        winner_label = tr(lang, "battle_first") if winner_num == "1" else tr(lang, "battle_second")
        report = f"**{tr(lang, 'battle_title')}**\n\n{tr(lang, 'battle_winner')} **{winner_label}**"
        await interaction.followup.send(content=report[:1900],
                                        file=discord.File(fp=img, filename="battle.png"))
    except Exception as e:
        logger.error(f"DS slash battle: {e}")
        await interaction.followup.send(f"Ошибка: {e}")


@app_commands.describe(image="Photo / Фото", advice="Include advice / Показать рекомендации")
async def ds_slash_femboy(interaction: discord.Interaction, image: discord.Attachment, advice: bool = False) -> None:
    await interaction.response.defer()
    chat_id = interaction.channel_id or 0
    user_id = interaction.user.id
    lang = ds_lang_of(interaction)
    try:
        img_bytes = await download_image_bytes(image.url)
        cfg = get_effective_config("ds", chat_id, user_id)
        theme = cfg.get("theme", "dark")
        ai_data = await get_femboy_data(img_bytes, advice, lang=lang)
        if "error" in ai_data:
            await interaction.followup.send(ai_data['error'])
            return
        infographic = await create_femboy_infographic(img_bytes, ai_data, theme=theme, lang=lang)
        report = (
            f"**{tr(lang, 'femboy_title')}**\n"
            f"{tr(lang, 'femboy_gender')} {ai_data.get('gender', '?')}\n"
            f"{tr(lang, 'femboy_score')} `{ai_data.get('fmb', '?')}/10.0`"
        )
        await interaction.followup.send(content=report[:1900],
                                        file=discord.File(fp=infographic, filename="femboy.png"))
    except Exception as e:
        logger.error(f"DS slash femboy: {e}")
        await interaction.followup.send(f"Ошибка: {e}")


@app_commands.describe(image1="First photo / Первое фото", image2="Second photo / Второе фото")
async def ds_slash_femboy_battle(interaction: discord.Interaction, image1: discord.Attachment, image2: discord.Attachment) -> None:
    await interaction.response.defer()
    chat_id = interaction.channel_id or 0
    user_id = interaction.user.id
    lang = ds_lang_of(interaction)
    try:
        p1 = await download_image_bytes(image1.url)
        p2 = await download_image_bytes(image2.url)
        cfg = get_effective_config("ds", chat_id, user_id)
        theme = cfg.get("theme", "dark")
        ai_data = await get_femboy_battle_data(p1, p2, lang=lang)
        if "error" in ai_data:
            await interaction.followup.send(ai_data['error'])
            return
        img = await create_femboy_battle_infographic(p1, p2, ai_data, theme=theme, lang=lang)
        winner_num = str(ai_data.get("winner", "1"))
        winner_label = tr(lang, "femboy_battle_first") if winner_num == "1" else tr(lang, "femboy_battle_second")
        report = f"**{tr(lang, 'femboy_battle_title')}**\n\n{tr(lang, 'femboy_battle_winner')} **{winner_label}**"
        await interaction.followup.send(content=report[:1900],
                                        file=discord.File(fp=img, filename="femboy_battle.png"))
    except Exception as e:
        logger.error(f"DS slash femboy battle: {e}")
        await interaction.followup.send(f"Ошибка: {e}")


async def ds_slash_groupinfo(interaction: discord.Interaction) -> None:
    lang = ds_lang_of(interaction)
    if interaction.guild is None:
        await interaction.response.send_message(
            "не в гильдии, че сказать" if lang == "ru" else "not in a guild, nothing to say",
            ephemeral=True,
        )
        return
    g = interaction.guild
    lines: list[str] = []
    lines.append(("Название: " if lang == "ru" else "Name: ") + (g.name or "?"))
    lines.append(f"ID: {g.id}")
    if g.owner_id:
        lines.append(f"Owner ID: {g.owner_id}")
    lines.append(("Участников: " if lang == "ru" else "Members: ") + str(g.member_count or "?"))
    lines.append(("Бустов: " if lang == "ru" else "Boosts: ") + str(g.premium_subscription_count or 0))
    created = g.created_at.strftime('%d.%m.%Y') if g.created_at else "?"
    lines.append(("Создан: " if lang == "ru" else "Created: ") + created)
    if g.description:
        lines.append(("Описание: " if lang == "ru" else "Description: ") + str(g.description)[:300])
    text = "\n".join(lines)
    await interaction.response.send_message(text[:1900])


@app_commands.describe(user="User to inspect / Пользователь")
async def ds_slash_userinfo(interaction: discord.Interaction, user: discord.Member | None = None) -> None:
    lang = ds_lang_of(interaction)
    target = user or interaction.user
    lines: list[str] = []
    lines.append(("Имя: " if lang == "ru" else "Name: ") + str(target.display_name))
    lines.append(f"Username: @{target.name}")
    lines.append(f"ID: {target.id}")
    if isinstance(target, discord.Member):
        if target.nick:
            lines.append(("Ник: " if lang == "ru" else "Nickname: ") + target.nick)
        if target.joined_at:
            lines.append(("Вступил: " if lang == "ru" else "Joined: ") + target.joined_at.strftime('%d.%m.%Y'))
        roles = [r.name for r in target.roles if r.name != "@everyone"]
        if roles:
            lines.append(("Роли: " if lang == "ru" else "Roles: ") + ", ".join(roles[:8]))
    if target.bot:
        lines.append(("Бот: " if lang == "ru" else "Bot: ") + ("да" if lang == "ru" else "yes"))
    await interaction.response.send_message("\n".join(lines)[:1900])
