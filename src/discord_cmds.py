# Kulsh GPT | v2.47.0
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
from src.billing import (
    DONATIONALERTS_PAGE,
    MIN_TOPUP_RUB,
    PRIVACY_URL,
    SUPPORT_ADMIN_DS,
    TERMS_URL,
    create_ticket,
    get_balance,
    get_topup_count,
    get_total_topup,
    map_admin_message,
    poll_donations_once,
    topup_code,
)
from src.charts import extract_chart_marker, render_infographic
from src.draw import process_drawing
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
    MODEL_GROUPS,
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
    is_paid_model,
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
    last_search_sources,
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


SEARCH_ANIM_EMOJIS = ("🗿", "🍷")


def _host_of(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return (urlparse(url).hostname or "").lstrip("www.")
    except Exception:
        return ""


async def search_with_anim_ds(message: discord.Message, query: str) -> list[Any]:
    """Анимация поиска в Discord: плейсхолдер → «читаю домен» → удаление."""
    status: discord.Message | None = None
    try:
        status = await message.reply("🗿 поиск в интернете...")
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
                await status.edit(content=f"{emoji} читаю {h}")
            except Exception:
                pass
            await asyncio.sleep(0.6)
        try:
            await status.delete()
        except Exception:
            pass
    return results


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


async def fetch_group_info_ds(message: discord.Message, lang: str = "ru") -> str | None:
    """Инфо о сервере/канале — Discord-аналог fetch_group_info_tg."""
    guild = message.guild
    if guild is None:
        return None
    lines: list[str] = []
    lines.append(("Название: " if lang == "ru" else "Name: ") + (guild.name or "?"))
    lines.append(f"ID: {guild.id}")
    if guild.owner_id:
        lines.append(("Владелец ID: " if lang == "ru" else "Owner ID: ") + str(guild.owner_id))
    lines.append(("Участников: " if lang == "ru" else "Members: ") + str(guild.member_count or "?"))
    lines.append(("Бустов: " if lang == "ru" else "Boosts: ") + str(guild.premium_subscription_count or 0))
    if guild.created_at:
        lines.append(("Создан: " if lang == "ru" else "Created: ") + guild.created_at.strftime('%d.%m.%Y'))
    if guild.description:
        lines.append(("Описание: " if lang == "ru" else "Description: ") + str(guild.description)[:300])
    lines.append(("Текущий канал: " if lang == "ru" else "Current channel: ")
                 + getattr(message.channel, "name", "?"))
    return "\n".join(lines)


async def fetch_user_info_ds(message: discord.Message, user_id: int, lang: str = "ru") -> str | None:
    """Инфо о пользователе — Discord-аналог fetch_user_info_tg."""
    target = None
    me = _ds_bot_user()
    if message.mentions:
        for m in message.mentions:
            if me is None or m.id != me.id:
                target = m
                break
    if target is None and message.reference and message.reference.resolved and isinstance(message.reference.resolved, discord.Message):
        target = message.reference.resolved.author
    if target is None and (message.guild is None or user_id == message.author.id):
        target = message.author
    if target is None and message.guild is not None:
        try:
            target = message.guild.get_member(user_id) or await message.guild.fetch_member(user_id)
        except Exception:
            target = None
    if target is None:
        return None
    lines: list[str] = []
    lines.append(("Имя: " if lang == "ru" else "Name: ") + str(getattr(target, "display_name", "?")))
    lines.append(f"@username: @{getattr(target, 'name', '?')}")
    lines.append(f"ID: {target.id}")
    nick = getattr(target, "nick", None)
    if nick:
        lines.append(("Ник: " if lang == "ru" else "Nickname: ") + str(nick))
    roles = getattr(target, "roles", None)
    if roles:
        role_names = [r.name for r in roles if r.name != "@everyone"]
        if role_names:
            lines.append(("Роли: " if lang == "ru" else "Roles: ") + ", ".join(role_names[:8]))
    joined = getattr(target, "joined_at", None)
    if joined:
        lines.append(("Вступил: " if lang == "ru" else "Joined: ") + joined.strftime('%d.%m.%Y'))
    if getattr(target, "bot", False):
        lines.append(("Бот: " if lang == "ru" else "Bot: ") + ("да" if lang == "ru" else "yes"))
    return "\n".join(lines)


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
            results = await search_with_anim_ds(message, query)
            if results:
                last_search_sources[f"ds_{chat_id}"] = results
                context = format_search_results(results)
                follow_prompt = (
                    f"Пользователь спросил: {orig_user_text}\n\n"
                    f"Ты выполнил поиск: {query}\n\nРезультаты:\n{context}\n\n"
                    f"Ответь на основе результатов, живо и по делу. Можешь использовать утилиты (!separate, !draw и др.). "
                    f"Ссылки вставлять не обязан — они уже у бота в контексте."
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

    # ---- draw / term ----
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
            logger.error(f"ds draw: {e}")

    clean_segments, markers = process_ai_response(
        draw_before if draw_png is not None else answer_raw,
        separate_enabled=separate_enabled,
    )

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
    if "group_info" in markers:
        markers.remove("group_info")
        try:
            info = await fetch_group_info_ds(message, lang=lang)
        except Exception as e:
            logger.warning(f"DS group_info: {e}")
            info = None
        if info:
            follow_prompt = (
                f"Пользователь попросил инфо о текущем сервере. Данные:\n{info}\n\n"
                f"Кратко перескажи в своём стиле. Маленькими буквами. Без маркеров."
            )
        else:
            follow_prompt = "Не удалось получить инфо о сервере. Скажи кратко."
        try:
            gi_answer = await ask_ai_async(prompt=follow_prompt, chat_id=chat_id, user_id=user_id, platform="ds")
            if gi_answer and gi_answer.strip():
                extra_segments.extend(clean_extra_text(gi_answer))
        except Exception as e:
            logger.warning(f"DS group_info ai: {e}")
    if "user_info" in markers:
        markers.remove("user_info")
        target_uid = user_id
        m_ui = re.search(r'!\s*user[\s_]*info\s*:?\s*(\d+)', answer_raw or "", re.IGNORECASE)
        if m_ui:
            try:
                target_uid = int(m_ui.group(1))
            except ValueError:
                target_uid = user_id
        try:
            info = await fetch_user_info_ds(message, target_uid, lang=lang)
        except Exception as e:
            logger.warning(f"DS user_info: {e}")
            info = None
        if info:
            follow_prompt = (
                f"Пользователь попросил инфо о пользователе id {target_uid}. Данные:\n{info}\n\n"
                f"Кратко перескажи в своём стиле. Без маркеров."
            )
        else:
            follow_prompt = "Не удалось получить инфо о пользователе. Скажи об этом."
        try:
            ui_answer = await ask_ai_async(prompt=follow_prompt, chat_id=chat_id, user_id=user_id, platform="ds")
            if ui_answer and ui_answer.strip():
                extra_segments.extend(clean_extra_text(ui_answer))
        except Exception as e:
            logger.warning(f"DS user_info ai: {e}")

    all_segments = clean_segments + extra_segments
    if draw_png is None and not all_segments:
        # Страховка: если в ответе был осмысленный текст, но он схлопнулся в ноль —
        # отправляем его как есть, чтобы ответ не пропал молча.
        fallback = scrub_stray_markers(answer_raw or "").strip()
        if fallback and not markers:
            all_segments = [fallback]
    if draw_png is None and not all_segments:
        for m in markers:
            if m in ("sticker", "gif"):
                try:
                    await execute_utility_ds(message, m, chat_id, user_id)
                except Exception as e:
                    logger.warning(f"ds utility: {e}")
        return

    sent_flag = [False]

    async def _send_seg(seg: str, idx: int) -> None:
        seg = scrub_stray_markers(seg)
        if cfg.get("communication_mode", "kent") == "kent":
            seg = strip_chat_emojis(seg)
        if not seg:
            return
        try:
            await typing_with_delay_ds(message.channel, seg, delay=calc_typing_delay(seg, segment_index=idx))
        except Exception:
            pass
        try:
            if idx == 0:
                try:
                    await message.reply(seg)
                except Exception as e_reply:
                    logger.warning(f"DS reply failed ({e_reply}); fallback to channel.send")
                    await message.channel.send(seg)
            else:
                await message.channel.send(seg)
            sent_flag[0] = True
            add_bot_memory(f"ds_{chat_id}", seg)
        except Exception as e:
            logger.error(
                f"❌ Не удалось отправить ответ в Discord (channel={chat_id}): {type(e).__name__}: {e}"
            )

    for i, seg in enumerate(all_segments):
        await _send_seg(seg, i)

    if draw_png is not None:
        after_segments, _after_markers = process_ai_response(draw_after, separate_enabled=separate_enabled)
        caption = ""
        if after_segments:
            caption = scrub_stray_markers(after_segments[0])
            if cfg.get("communication_mode", "kent") == "kent":
                caption = strip_chat_emojis(caption)
            caption = caption[:1990]
        try:
            await message.reply(file=discord.File(fp=draw_png, filename="drawing.png"), content=caption or None)
            sent_flag[0] = True
            add_bot_memory(f"ds_{chat_id}", "[нарисовал картинку]" + (f" {caption}" if caption else ""))
        except Exception as e:
            logger.error(f"ds draw send: {e}")
        for j, seg in enumerate(after_segments[1:], start=1):
            await _send_seg(seg, j)

    if not sent_flag[0]:
        logger.error(
            f"❌ Ответ сформирован, но НЕ отправлен (channel={chat_id}, "
            f"segments={len(all_segments)}). Проверь права бота: Send Messages / Embed Links / "
            f"Attach Files / Read Message History в этом канале."
        )

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
    drawing = tr(lang, "on") if cfg.get("drawing_enabled", True) else tr(lang, "off")
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
        embed.add_field(name="💬 Разбивка", value=sep, inline=True)
        embed.add_field(name="😀 Реакции", value=reactions, inline=True)
        embed.add_field(name="🔎 Веб-поиск", value=websearch, inline=True)
        embed.add_field(name="🎨 Рисование", value=drawing, inline=True)
        embed.add_field(name="🎨 Стикеры/гифки", value=stickers, inline=True)
        embed.add_field(name="🗣 Автоответ", value=autoreply, inline=True)
        embed.add_field(name="📢 Случайные", value=random_msgs, inline=True)
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
        embed.add_field(name="💬 Split", value=sep, inline=True)
        embed.add_field(name="😀 Reactions", value=reactions, inline=True)
        embed.add_field(name="🔎 Web search", value=websearch, inline=True)
        embed.add_field(name="🎨 Drawing", value=drawing, inline=True)
        embed.add_field(name="🎨 Stickers/GIFs", value=stickers, inline=True)
        embed.add_field(name="🗣 Auto-reply", value=autoreply, inline=True)
        embed.add_field(name="📢 Random", value=random_msgs, inline=True)
        embed.add_field(name="🎬 Series", value=series, inline=True)
        embed.add_field(name="📝 Custom prompt", value=prompt, inline=False)
    return embed


# ============================================================
# INTERACTIVE CONFIG VIEW (buttons + selects, TG-style UX)
# ============================================================
def _cfg_lang(chat_id: int, user_id: int) -> str:
    return str(get_effective_config("ds", chat_id, user_id).get("language", "ru"))


def _bool_label(cfg: JsonDict, key: str, default: bool = True) -> str:
    return "✅" if cfg.get(key, default) else "❌"


class DsConfigView(discord.ui.View):
    """Интерактивная панель настроек (аналог TG-клавиатуры).

    Discord-ограничения: одна action-row = либо до 5 кнопок, либо ровно один
    select. Всего не больше 5 строк на сообщение. Поэтому — один главный
    select-навигатор + кнопки, а выбор значений открывается в под-вьюхе.
    """

    def __init__(self, chat_id: int, user_id: int, is_admin: bool, is_dm: bool = False) -> None:
        super().__init__(timeout=600)
        self.chat_id = chat_id
        self.user_id = user_id
        self.is_admin = is_admin
        self.is_dm = is_dm
        self._rebuild()

    # --- helpers ---
    def _scope(self) -> str:
        return get_ds_scope(self.chat_id)

    def _can_edit(self) -> bool:
        return self.is_admin or self._scope() == "self"

    def _write(self) -> JsonDict:
        return get_write_config("ds", self.chat_id, self.user_id)

    def _lang(self) -> str:
        return str(get_effective_config("ds", self.chat_id, self.user_id).get("language", "ru"))

    def _rebuild(self) -> None:
        self.clear_items()
        cfg = get_effective_config("ds", self.chat_id, self.user_id)
        lang = self._lang()
        disabled = not self._can_edit()

        def b(key: str, default: bool = True) -> str:
            return "✅" if cfg.get(key, default) else "❌"

        theme_disp = tr(lang, "dark") if cfg.get("theme", "dark") == "dark" else tr(lang, "light")
        mode_raw = str(cfg.get("communication_mode", "kent"))
        mode_disp = (tr(lang, "mode_assistant") if mode_raw == "assistant"
                     else (tr(lang, "mode_pro") if mode_raw == "pro" else tr(lang, "mode_kent")))
        model_disp = model_display_name(cfg.get("model"), lang)

        options = [
            discord.SelectOption(label=f"{tr(lang, 'cfg_lang')}: {tr(lang, 'russian') if lang == 'ru' else tr(lang, 'english')}", value="lang"),
            discord.SelectOption(label=f"{tr(lang, 'cfg_theme')}: {theme_disp}", value="theme"),
            discord.SelectOption(label=f"{tr(lang, 'cfg_mode')}: {mode_disp}", value="mode"),
            discord.SelectOption(label=f"{tr(lang, 'cfg_model')}: {model_disp}", value="model"),
            discord.SelectOption(label=f"{tr(lang, 'cfg_sep')}: {b('separate_enabled')}", value="separate_enabled"),
            discord.SelectOption(label=f"{tr(lang, 'cfg_reactions')}: {b('reactions_enabled')}", value="reactions_enabled"),
            discord.SelectOption(label=f"{tr(lang, 'cfg_websearch')}: {b('web_search_enabled')}", value="web_search_enabled"),
            discord.SelectOption(label=f"{tr(lang, 'cfg_drawing')}: {b('drawing_enabled')}", value="drawing_enabled"),
            discord.SelectOption(label=f"{tr(lang, 'cfg_stickers')}: {b('stickers_enabled')}", value="stickers_enabled"),
            discord.SelectOption(label=f"{tr(lang, 'cfg_autoreply')}: {b('random_reply_enabled', False)}", value="random_reply_enabled"),
            discord.SelectOption(label=f"{tr(lang, 'cfg_random')}: {b('random_messages_enabled')}", value="random_messages_enabled"),
            discord.SelectOption(label=tr(lang, "cfg_edit_prompt"), value="prompt"),
        ]
        main_sel = discord.ui.Select(placeholder=tr(lang, "ds_menu_placeholder"),
                                     options=options, row=0, disabled=disabled)
        main_sel.callback = self._on_main
        self.add_item(main_sel)

        b_prompt = discord.ui.Button(label=tr(lang, "cfg_edit_prompt"),
                                     style=discord.ButtonStyle.primary, row=1, disabled=disabled)
        b_prompt.callback = self._on_prompt
        self.add_item(b_prompt)

        b_reset_mem = discord.ui.Button(label=tr(lang, "cfg_reset_memory"),
                                        style=discord.ButtonStyle.danger, row=1, disabled=disabled)
        b_reset_mem.callback = self._on_reset_memory
        self.add_item(b_reset_mem)

        b_reset_prompt = discord.ui.Button(label=tr(lang, "cfg_reset_prompt"),
                                           style=discord.ButtonStyle.danger, row=1, disabled=disabled)
        b_reset_prompt.callback = self._on_reset_prompt
        self.add_item(b_reset_prompt)

        b_apply = discord.ui.Button(label=tr(lang, "cfg_apply_close"),
                                    style=discord.ButtonStyle.success, row=2)
        b_apply.callback = self._on_apply
        self.add_item(b_apply)

        if self.is_admin:
            scope = self._scope()
            scope_label = ("🌐 " + ("Общие" if lang == "ru" else "Shared")) if scope == "shared" \
                else ("👤 " + ("Личные" if lang == "ru" else "Per-user"))
            b_scope = discord.ui.Button(label=scope_label, style=discord.ButtonStyle.secondary, row=2)
            b_scope.callback = self._on_scope
            self.add_item(b_scope)

    # --- shared helpers ---
    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(tr(self._lang(), "cfg_not_yours"), ephemeral=True)
            return False
        if not self._can_edit():
            await interaction.response.send_message(tr(self._lang(), "ds_only_admins"), ephemeral=True)
            return False
        return True

    async def _refresh_main(self, interaction: discord.Interaction) -> None:
        self._rebuild()
        embed = ds_config_embed(self.chat_id, self.user_id)
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception:
            try:
                await interaction.edit_original_response(embed=embed, view=self)
            except Exception:
                pass

    async def _open_choice(self, interaction: discord.Interaction, kind: str) -> None:
        self._rebuild()
        sub = DsChoiceView(self, kind)
        embed = ds_config_embed(self.chat_id, self.user_id)
        try:
            await interaction.response.edit_message(embed=embed, view=sub)
        except Exception:
            try:
                await interaction.edit_original_response(embed=embed, view=sub)
            except Exception:
                pass

    async def _on_main(self, interaction: discord.Interaction) -> None:
        if not await self._guard(interaction):
            return
        value = interaction.data["values"][0]
        toggle_keys = {
            "separate_enabled": True, "reactions_enabled": True, "web_search_enabled": True,
            "drawing_enabled": True,
            "stickers_enabled": True, "random_reply_enabled": False, "random_messages_enabled": True,
        }
        if value in toggle_keys:
            cfg = self._write()
            cfg[value] = not cfg.get(value, toggle_keys[value])
            if cfg.get("separate_enabled", True) and cfg.get("streaming_enabled", False):
                cfg["streaming_enabled"] = False
            save_user_configs()
            await self._refresh_main(interaction)
            return
        if value == "prompt":
            await self._on_prompt(interaction)
            return
        if value in ("lang", "theme", "mode", "model"):
            await self._open_choice(interaction, value)
            return
        await self._refresh_main(interaction)

    async def _on_prompt(self, interaction: discord.Interaction) -> None:
        if not await self._guard(interaction):
            return
        lang = self._lang()
        await interaction.response.send_message(tr(lang, "ds_prompt_ask"), ephemeral=True)
        try:
            msg = await interaction.client.wait_for(  # type: ignore[union-attr]
                "message",
                check=lambda m: m.author.id == self.user_id and m.channel.id == interaction.channel_id,
                timeout=180,
            )
        except Exception:
            return
        text = (msg.content or "").strip()
        cfg = self._write()
        if text.lower() in ("отмена", "cancel", "сброс", "reset"):
            cfg["custom_prompt"] = None
            save_user_configs()
            await msg.reply(tr(lang, "cfg_prompt_reset"))
        elif text:
            cfg["custom_prompt"] = text[:2000]
            save_user_configs()
            await msg.reply(tr(lang, "prompt_saved", len(text)))
        try:
            await msg.delete()
        except Exception:
            pass

    async def _on_reset_memory(self, interaction: discord.Interaction) -> None:
        if not await self._guard(interaction):
            return
        lang = self._lang()
        from src.util import long_term_memory, save_long_term_memory
        long_term_memory.pop(str(self.chat_id), None)
        try:
            save_long_term_memory(long_term_memory)
        except Exception:
            pass
        await interaction.response.send_message(tr(lang, "cfg_memory_reset"), ephemeral=True)

    async def _on_reset_prompt(self, interaction: discord.Interaction) -> None:
        if not await self._guard(interaction):
            return
        self._write()["custom_prompt"] = None
        save_user_configs()
        await self._refresh_main(interaction)

    async def _on_scope(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(tr(self._lang(), "cfg_not_yours"), ephemeral=True)
            return
        if not self.is_admin:
            await interaction.response.send_message(tr(self._lang(), "ds_only_admins"), ephemeral=True)
            return
        new_scope = "self" if self._scope() == "shared" else "shared"
        set_ds_scope(self.chat_id, new_scope)
        await self._refresh_main(interaction)

    async def _on_apply(self, interaction: discord.Interaction) -> None:
        lang = self._lang()
        save_user_configs()
        try:
            await interaction.response.edit_message(
                embed=ds_config_embed(self.chat_id, self.user_id), view=None,
            )
            await interaction.followup.send(tr(lang, "cfg_done"), ephemeral=True)
            return
        except Exception:
            pass
        try:
            await interaction.response.defer()
            await interaction.edit_original_response(
                embed=ds_config_embed(self.chat_id, self.user_id), view=None,
            )
            await interaction.followup.send(tr(lang, "cfg_done"), ephemeral=True)
        except Exception:
            pass


class DsChoiceView(discord.ui.View):
    """Под-вьюха выбора значения (язык/тема/режим/модель/температура)."""

    def __init__(self, parent: DsConfigView, kind: str) -> None:
        super().__init__(timeout=600)
        self.parent = parent
        self.kind = kind
        self._build()

    def _build(self) -> None:
        self.clear_items()
        p = self.parent
        cfg = get_effective_config("ds", p.chat_id, p.user_id)
        lang = p._lang()
        cur = None
        options: list[discord.SelectOption] = []
        if self.kind == "lang":
            cur = cfg.get("language", "ru")
            options = [
                discord.SelectOption(label="Русский 🇷🇺", value="ru", default=cur == "ru"),
                discord.SelectOption(label="English 🇬🇧", value="en", default=cur == "en"),
            ]
            placeholder = tr(lang, "cfg_lang")
        elif self.kind == "theme":
            cur = cfg.get("theme", "dark")
            options = [
                discord.SelectOption(label=("Тёмная 🌑" if lang == "ru" else "Dark 🌑"), value="dark", default=cur == "dark"),
                discord.SelectOption(label=("Светлая ☀️" if lang == "ru" else "Light ☀️"), value="light", default=cur == "light"),
            ]
            placeholder = tr(lang, "cfg_theme")
        elif self.kind == "mode":
            cur = str(cfg.get("communication_mode", "kent"))
            options = [
                discord.SelectOption(label=tr(lang, "mode_kent"), value="kent", default=cur == "kent"),
                discord.SelectOption(label=tr(lang, "mode_assistant"), value="assistant", default=cur == "assistant"),
            ]
            if p.is_dm:
                options.append(discord.SelectOption(label=tr(lang, "mode_pro"), value="pro", default=cur == "pro"))
            placeholder = tr(lang, "cfg_choose_mode")
        elif self.kind == "model":
            cur = cfg.get("model")
            options = [discord.SelectOption(
                label=tr(lang, "cfg_auto"), value="auto", default=not cur,
                description=tr(lang, "cfg_auto_hint")[:100],
            )]
            for i, (company, models) in enumerate(MODEL_GROUPS):
                has_current = bool(cur and cur in models)
                options.append(discord.SelectOption(
                    label=company,
                    value=f"co:{i}",
                    default=has_current,
                    description=tr(lang, "cfg_company")[:100],
                ))
            placeholder = tr(lang, "cfg_choose_model")
        else:
            placeholder = tr(lang, "cfg_choose_model")

        sel = discord.ui.Select(placeholder=placeholder, options=options[:25], row=0)
        sel.callback = self._on_select
        self.add_item(sel)

        back = discord.ui.Button(label=tr(lang, "cfg_back"), style=discord.ButtonStyle.primary, row=1)
        back.callback = self._on_back
        self.add_item(back)

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.parent.user_id:
            await interaction.response.send_message(tr(self.parent._lang(), "cfg_not_yours"), ephemeral=True)
            return False
        return True

    async def _on_select(self, interaction: discord.Interaction) -> None:
        if not await self._guard(interaction):
            return
        p = self.parent
        val = interaction.data["values"][0]
        cfg = p._write()
        if self.kind == "lang":
            cfg["language"] = val
        elif self.kind == "theme":
            cfg["theme"] = val
        elif self.kind == "mode":
            if val == "pro" and not p.is_dm:
                await interaction.response.send_message(tr(p._lang(), "mode_need_dm"), ephemeral=True)
                return
            cfg["communication_mode"] = val
        elif self.kind == "model":
            if val == "auto":
                cfg["model"] = None
                save_user_configs()
                await p._open_choice(interaction, "model")
                return
            if val.startswith("co:"):
                try:
                    company_index = int(val.split(":", 1)[1])
                except ValueError:
                    company_index = 0
                await interaction.response.edit_message(
                    embed=ds_config_embed(p.chat_id, p.user_id),
                    view=DsModelView(p, company_index),
                )
                return
            return
        else:
            return
        save_user_configs()
        await p._open_choice(interaction, self.kind)

    async def _on_back(self, interaction: discord.Interaction) -> None:
        if not await self._guard(interaction):
            return
        await self.parent._refresh_main(interaction)


class DsModelView(discord.ui.View):
    """Модели выбранной компании + возврат к списку компаний."""

    def __init__(self, parent: DsConfigView, company_index: int) -> None:
        super().__init__(timeout=600)
        self.parent = parent
        self.company_index = max(0, min(company_index, len(MODEL_GROUPS) - 1))
        self._build()

    def _build(self) -> None:
        p = self.parent
        lang = p._lang()
        cfg = get_effective_config("ds", p.chat_id, p.user_id)
        cur = cfg.get("model")
        company, models = MODEL_GROUPS[self.company_index]
        options: list[discord.SelectOption] = []
        for m in models:
            if m not in MODEL_LIST:
                continue
            idx = MODEL_LIST.index(m)
            label = MODEL_DISPLAY.get(m, m) + (" 💎" if is_paid_model(m) else "")
            options.append(discord.SelectOption(
                label=label[:100], value=str(idx), default=cur == m,
            ))
        sel = discord.ui.Select(placeholder=company[:100], options=options[:25], row=0)
        sel.callback = self._on_select
        self.add_item(sel)

        back = discord.ui.Button(label=tr(lang, "cfg_back"), style=discord.ButtonStyle.primary, row=1)
        back.callback = self._on_back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.parent.user_id:
            await interaction.response.send_message(
                tr(self.parent._lang(), "cfg_not_yours"), ephemeral=True,
            )
            return False
        return True

    async def _on_select(self, interaction: discord.Interaction) -> None:
        val = interaction.data["values"][0]
        cfg = self.parent._write()
        try:
            cfg["model"] = MODEL_LIST[int(val)]
        except (ValueError, IndexError):
            return
        save_user_configs()
        await interaction.response.edit_message(
            embed=ds_config_embed(self.parent.chat_id, self.parent.user_id),
            view=DsModelView(self.parent, self.company_index),
        )

    async def _on_back(self, interaction: discord.Interaction) -> None:
        await self.parent._open_choice(interaction, "model")


async def ds_handle_config(message: discord.Message, user_id: int) -> None:
    chat_id = message.channel.id
    member = as_member(message.author)
    is_dm = message.guild is None
    is_admin = bool(member and member.guild_permissions.administrator) if message.guild else True
    embed = ds_config_embed(chat_id, user_id)
    view = DsConfigView(chat_id, user_id, is_admin, is_dm=is_dm)
    await message.reply(embed=embed, view=view)


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
    elif param in ("рисование", "drawing", "draw"):
        cfg["drawing_enabled"] = bool_on; save_user_configs()
        await message.reply(tr(lang, "ds_setting_drawing", tr(lang, "on") if bool_on else tr(lang, "off")))
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
            "Опенсорсный ИИ-бот с характером.\n\n"
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
            "Опенсорсный ИИ-бот с характером.\n\n"
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


class DsMenuView(discord.ui.View):
    """Меню как в TG: настройки, команды, донат, GitHub, MINI APP-ссылка."""

    def __init__(self, lang: str) -> None:
        super().__init__(timeout=600)
        self.lang = lang

        b_settings = discord.ui.Button(label=tr(lang, "btn_settings"),
                                       style=discord.ButtonStyle.success, row=0)
        b_settings.callback = self._on_settings
        self.add_item(b_settings)

        b_cmds = discord.ui.Button(label=tr(lang, "btn_commands"),
                                   style=discord.ButtonStyle.primary, row=0)
        b_cmds.callback = self._on_help
        self.add_item(b_cmds)

        self.add_item(discord.ui.Button(label=tr(lang, "btn_donate"),
                                        style=discord.ButtonStyle.link, url=DONATE_URL, row=1))
        self.add_item(discord.ui.Button(label=tr(lang, "btn_github"),
                                        style=discord.ButtonStyle.link, url=GITHUB_URL, row=1))
        self.add_item(discord.ui.Button(label="🚀 Mini App",
                                        style=discord.ButtonStyle.link, url=MINI_APP_URL, row=2))
        b_balance = discord.ui.Button(label=tr(lang, "btn_balance"),
                                      style=discord.ButtonStyle.primary, row=2)
        b_balance.callback = self._on_balance
        self.add_item(b_balance)

    async def _on_balance(self, interaction: discord.Interaction) -> None:
        nick = getattr(interaction.user, "display_name", None) or interaction.user.name
        embed = _ds_balance_embed(self.lang, interaction.user.id, nick)
        view = DsBalanceView(interaction.user.id, self.lang, nick)
        if interaction.guild is None:
            await interaction.response.defer()
            await interaction.edit_original_response(embed=embed, view=view)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await interaction.user.send(embed=embed, view=view)
            await interaction.followup.send("🍷 Меню баланса — у тебя в личке", ephemeral=True)
        except Exception:
            await interaction.followup.send(
                "Не смог написать тебе в личку. Разреши личные сообщения от участников сервера.",
                ephemeral=True,
            )

    async def _on_settings(self, interaction: discord.Interaction) -> None:
        chat_id = interaction.channel_id or 0
        user_id = interaction.user.id
        is_admin = True
        member = as_member(interaction.user)
        if interaction.guild:
            is_admin = bool(member and member.guild_permissions.administrator)
        view = DsConfigView(chat_id, user_id, is_admin, is_dm=interaction.guild is None)
        embed = ds_config_embed(chat_id, user_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _on_help(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(ds_help_text(self.lang), ephemeral=True)


async def ds_slash_start(interaction: discord.Interaction) -> None:
    lang = ds_lang_of(interaction)
    view = DsMenuView(lang)
    await interaction.response.send_message(ds_start_text(lang), view=view)


async def ds_slash_menu(interaction: discord.Interaction) -> None:
    lang = ds_lang_of(interaction)
    view = DsMenuView(lang)
    await interaction.response.send_message(ds_menu_text(lang), view=view)


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
        f"- {tr(lang, 'donate_online')}: {DONATE_URL}"
    )
    await interaction.response.send_message(text)


async def ds_slash_credits(interaction: discord.Interaction) -> None:
    lang = ds_lang_of(interaction)
    creds = get_user_credits("ds", interaction.user.id)
    await interaction.response.send_message(tr(lang, "credits_balance", creds, DAILY_CREDITS))


# ============================================================
# BALANCE / PROFILE / SUPPORT
# ============================================================
def _ds_money(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def _ds_balance_embed(lang: str, user_id: int, nick: str) -> discord.Embed:
    bal = _ds_money(get_balance("ds", user_id))
    total = _ds_money(get_total_topup("ds", user_id))
    if lang == "ru":
        desc = (
            f"Привет, **{nick}** 👋\n\n"
            f"**Баланс:** {bal} ₽\n"
            f"**Всего пополнено:** {total} ₽\n\n"
            f"**Пополнение**\n"
            f"- **Минимум:** {MIN_TOPUP_RUB:.0f} ₽\n"
            f"- **Код для оплаты:** `{topup_code('ds', user_id)}`\n"
            f"- **Способ:** кнопка «Пополнить» ниже\n\n"
            f"Скопируй код и вставь его в поле «Сообщение» при оплате. "
            f"Без кода платёж не привяжется к аккаунту.\n\n"
            f"*Обычно платёж зачисляется автоматически. Если этого не произошло — "
            f"нажми «Проверить платёж».*\n\n"
            f"[Пользовательское соглашение]({TERMS_URL}) · [Политика конфиденциальности]({PRIVACY_URL})"
        )
        title = "💳 Баланс"
    else:
        desc = (
            f"Hey, **{nick}** 👋\n\n"
            f"**Balance:** {bal} ₽\n"
            f"**Total topped up:** {total} ₽\n\n"
            f"**Top up**\n"
            f"- **Minimum:** {MIN_TOPUP_RUB:.0f} ₽\n"
            f"- **Payment code:** `{topup_code('ds', user_id)}`\n"
            f"- **Method:** the “Top up” button below\n\n"
            f"Copy the code into the donation message. Without it the payment won't be linked to your account.\n\n"
            f"*Usually credited automatically. If it didn't happen — press “Check payment”.*\n\n"
            f"[Terms of Service]({TERMS_URL}) · [Privacy Policy]({PRIVACY_URL})"
        )
        title = "💳 Balance"
    embed = discord.Embed(title=title, description=desc, color=0xA75FFF)
    return embed


def _ds_profile_embed(lang: str, user_id: int, nick: str) -> discord.Embed:
    bal = _ds_money(get_balance("ds", user_id))
    total = _ds_money(get_total_topup("ds", user_id))
    count = get_topup_count("ds", user_id)
    if lang == "ru":
        desc = (
            f"**{nick}**\n\n"
            f"**Discord ID:** `{user_id}`\n"
            f"**Баланс:** {bal} ₽\n"
            f"**Всего пополнено:** {total} ₽\n"
            f"**Пополнений:** {count}\n\n"
            f"*Пополнение и история платежей — в разделе баланса.*\n\n"
            f"[Пользовательское соглашение]({TERMS_URL}) · [Политика конфиденциальности]({PRIVACY_URL})"
        )
        title = "👤 Профиль"
    else:
        desc = (
            f"**{nick}**\n\n"
            f"**Discord ID:** `{user_id}`\n"
            f"**Balance:** {bal} ₽\n"
            f"**Total topped up:** {total} ₽\n"
            f"**Top-ups:** {count}\n\n"
            f"*Top-ups and payment history live in the balance section.*\n\n"
            f"[Terms of Service]({TERMS_URL}) · [Privacy Policy]({PRIVACY_URL})"
        )
        title = "👤 Profile"
    embed = discord.Embed(title=title, description=desc, color=0xA75FFF)
    return embed


class SupportModal(discord.ui.Modal, title="Поддержка / Support"):
    text: discord.ui.TextInput = discord.ui.TextInput(
        label="Опиши проблему / Describe the issue",
        style=discord.TextStyle.paragraph,
        max_length=1500,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        tid = create_ticket("ds", interaction.user.id, interaction.channel_id or 0, str(self.text.value))
        await interaction.response.send_message(
            f"Обращение №{tid} принято. Ответ придёт сюда.", ephemeral=True,
        )
        admin_id = SUPPORT_ADMIN_DS or (AUTHORIZED_UPDATERS[0] if AUTHORIZED_UPDATERS else 0)
        if not (admin_id and ds_bot is not None):
            return
        try:
            admin = ds_bot.get_user(admin_id) or await ds_bot.fetch_user(admin_id)
            sent = await admin.send(
                f"🎫 Обращение №{tid}\nПлатформа: Discord\nПользователь: {interaction.user.id}\n\n"
                f"{self.text.value}\n\n↩️ Ответь на это сообщение, чтобы передать ответ пользователю."
            )
            map_admin_message("ds", sent.id, tid)
        except Exception as e:
            logger.warning(f"ds support admin: {e}")


class DsProfileView(discord.ui.View):
    def __init__(self, user_id: int, lang: str, nick: str) -> None:
        super().__init__(timeout=600)
        self.user_id = user_id
        self.lang = lang
        self.nick = nick
        pay_url = DONATIONALERTS_PAGE or DONATE_URL
        self.add_item(discord.ui.Button(
            label=("💳 Пополнить" if lang == "ru" else "💳 Top up"),
            style=discord.ButtonStyle.link, url=pay_url, row=0,
        ))
        back = discord.ui.Button(
            label=("⬅️ Назад" if lang == "ru" else "⬅️ Back"),
            style=discord.ButtonStyle.primary, row=1,
        )
        back.callback = self._on_back
        self.add_item(back)
        support = discord.ui.Button(
            label=("💬 Поддержка" if lang == "ru" else "💬 Support"),
            style=discord.ButtonStyle.secondary, row=1,
        )
        support.callback = self._on_support
        self.add_item(support)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                ("Это не твоё меню 🤚" if self.lang == "ru" else "Not your menu 🤚"),
                ephemeral=True,
            )
            return False
        return True

    async def _on_back(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await interaction.edit_original_response(
            embed=_ds_balance_embed(self.lang, self.user_id, self.nick),
            view=DsBalanceView(self.user_id, self.lang, self.nick),
        )

    async def _on_support(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(SupportModal())


class DsBalanceView(discord.ui.View):
    def __init__(self, user_id: int, lang: str, nick: str) -> None:
        super().__init__(timeout=600)
        self.user_id = user_id
        self.lang = lang
        self.nick = nick
        pay_url = DONATIONALERTS_PAGE or DONATE_URL
        self.add_item(discord.ui.Button(
            label=("💳 Пополнить" if lang == "ru" else "💳 Top up"),
            style=discord.ButtonStyle.link, url=pay_url, row=0,
        ))
        profile = discord.ui.Button(
            label=("👤 Профиль" if lang == "ru" else "👤 Profile"),
            style=discord.ButtonStyle.primary, row=1,
        )
        profile.callback = self._on_profile
        self.add_item(profile)
        check = discord.ui.Button(
            label=("🔄 Проверить платёж" if lang == "ru" else "🔄 Check payment"),
            style=discord.ButtonStyle.secondary, row=1,
        )
        check.callback = self._on_check
        self.add_item(check)
        support = discord.ui.Button(
            label=("💬 Поддержка" if lang == "ru" else "💬 Support"),
            style=discord.ButtonStyle.secondary, row=2,
        )
        support.callback = self._on_support
        self.add_item(support)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                ("Это не твоё меню 🤚" if self.lang == "ru" else "Not your menu 🤚"),
                ephemeral=True,
            )
            return False
        return True

    async def _on_profile(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await interaction.edit_original_response(
            embed=_ds_profile_embed(self.lang, self.user_id, self.nick),
            view=DsProfileView(self.user_id, self.lang, self.nick),
        )

    async def _on_check(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        credited = await poll_donations_once()
        mine = [c for c in credited if c[0] == "ds" and c[1] == self.user_id]
        if mine:
            total = sum(c[2] for c in mine)
            text = (f"Зачислено: +{total:.2f} ₽" if self.lang == "ru" else f"Credited: +{total:.2f} ₽")
        else:
            text = ("Новых платежей не видно. Если донат был только что — подожди минуту и проверь ещё раз."
                    if self.lang == "ru" else
                    "No new payments yet. If you just donated, wait a minute and check again.")
        await interaction.followup.send(text, ephemeral=True)

    async def _on_support(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(SupportModal())


async def ds_slash_balance(interaction: discord.Interaction) -> None:
    lang = ds_lang_of(interaction)
    nick = getattr(interaction.user, "display_name", None) or interaction.user.name
    embed = _ds_balance_embed(lang, interaction.user.id, nick)
    view = DsBalanceView(interaction.user.id, lang, nick)
    if interaction.guild is None:
        await interaction.response.send_message(embed=embed, view=view)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        await interaction.user.send(embed=embed, view=view)
        await interaction.followup.send("🍷 Меню баланса — у тебя в личке", ephemeral=True)
    except Exception:
        await interaction.followup.send(
            "Не смог написать тебе в личку. Разреши личные сообщения от участников сервера.",
            ephemeral=True,
        )


async def ds_slash_profile(interaction: discord.Interaction) -> None:
    lang = ds_lang_of(interaction)
    nick = getattr(interaction.user, "display_name", None) or interaction.user.name
    embed = _ds_profile_embed(lang, interaction.user.id, nick)
    view = DsProfileView(interaction.user.id, lang, nick)
    if interaction.guild is None:
        await interaction.response.send_message(embed=embed, view=view)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        await interaction.user.send(embed=embed, view=view)
        await interaction.followup.send("🍷 Профиль — у тебя в личке", ephemeral=True)
    except Exception:
        await interaction.followup.send(
            "Не смог написать тебе в личку. Разреши личные сообщения от участников сервера.",
            ephemeral=True,
        )


@app_commands.describe(text="Описание проблемы / Issue description")
async def ds_slash_support(interaction: discord.Interaction, text: str | None = None) -> None:
    lang = ds_lang_of(interaction)
    if not text:
        await interaction.response.send_message(
            "Напиши так: `/support текст=опиши проблему`" if lang == "ru"
            else "Use `/support text=describe the issue`",
            ephemeral=True,
        )
        return
    tid = create_ticket("ds", interaction.user.id, interaction.channel_id or 0, text)
    await interaction.response.send_message(
        f"Обращение №{tid} принято. Ответ придёт сюда.", ephemeral=True,
    )
    admin_id = SUPPORT_ADMIN_DS or (AUTHORIZED_UPDATERS[0] if AUTHORIZED_UPDATERS else 0)
    if not (admin_id and ds_bot is not None):
        return
    try:
        admin = ds_bot.get_user(admin_id) or await ds_bot.fetch_user(admin_id)
        sent = await admin.send(
            f"🎫 Обращение №{tid}\nПлатформа: Discord\nПользователь: {interaction.user.id}\n\n"
            f"{text}\n\n↩️ Ответь на это сообщение, чтобы передать ответ пользователю."
        )
        map_admin_message("ds", sent.id, tid)
    except Exception as e:
        logger.warning(f"ds support admin: {e}")



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
    is_dm = interaction.guild is None
    view = DsConfigView(chat_id, user_id, is_admin, is_dm=is_dm)
    embed = ds_config_embed(chat_id, user_id)
    if cur_scope == "shared" and not is_admin:
        # не админ — видит настройки, но кнопки неактивны
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        return
    await interaction.response.send_message(embed=embed, view=view, ephemeral=not is_admin)


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
