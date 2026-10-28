# Kulsh GPT | v2.48.0
# by (main author): starf6ll
# coauthor & bot hosting: pomidorka1515

"""Discord message handler and voice sink."""

import asyncio
import json
import os
import re
import random
import time
from io import BytesIO
from typing import Any, cast

import discord

from src.ai import format_search_results, ask_ai_async, extract_memory, web_search
from src.charts import render_infographic
from src.discord_cmds import (
    ds_handle_config,
    ds_handle_config_param,
    get_avatar_description_ds,
    search_with_anim_ds,
    send_ds_ai_response,
)
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
from src.telegram import should_random_reply
from src.billing import (
    SUPPORT_ADMIN_DS,
    append_ticket_message,
    get_ticket,
    ticket_by_admin_message,
)
from src import admin_panel
from src.util import (
    JsonDict,
    perform_safe_git_update,
    voice_recognition_enabled,
    voice_recv_available,
    AudioSegment,
    tr,
    voice_client,
    add_media_history,
    add_user_memory,
    download_image_bytes,
    get_chat_memory,
    get_effective_config,
    get_top_donators,
    is_femboy_battle_command,
    is_femboy_rate_command,
    last_bot_reply,
    last_random_reply,
    logger,
    memory_to_messages,
    read_log_tail,
    sr,
    voice_recv,
    voice_text_channels,

    AUTHORIZED_UPDATERS,
    DONATE_URL,
    chunk_text,
    clean_extra_text,
    clean_json_text,
    extract_video_frame,
    is_battle_command,
    is_looksmaxxing_command,
    last_search_sources,
    register_ds_channel,
    process_ai_response,
    scrub_stray_markers,
    strip_chat_emojis,
    note_chat_participant,
)
from src import discord_cmds as dcmd


_scanned_guilds: set[int] = set()


async def _is_addressed_from_bot_ds(message: discord.Message) -> bool:
    me = dcmd.ds_bot.user if dcmd.ds_bot else None
    if me is None:
        return False
    if message.reference and message.reference.resolved and isinstance(message.reference.resolved, discord.Message):
        if message.reference.resolved.author == me:
            return True
    content = (message.content or "").lower()
    if "кульш" in content or "kulsh" in content:
        return True
    try:
        if me.mention in message.content:
            return True
    except Exception:
        pass
    try:
        if me.name.lower() in content:
            return True
    except Exception:
        pass
    return False


async def on_message(message: discord.Message) -> None:
    if message.author == dcmd.ds_bot.user:
        return
    guild = message.guild
    is_dm = message.guild is None
    # ВАЖНО: chat_id всегда channel.id, чтобы совпадать с настройками.
    chat_id = message.channel.id
    user_id = message.author.id
    register_ds_channel(chat_id, guild.id if guild else None)
    content = (message.content or "").strip()
    if admin_panel.is_secret_command(content):
        if admin_panel.is_admin_ds(user_id):
            await admin_panel.open_ds(message)
        return
    if await admin_panel.take_admin_ds(message):
        return
    if admin_panel.is_blocked("ds", user_id) and not admin_panel.is_admin_ds(user_id):
        return
    admin_panel.touch_user(
        "ds", user_id,
        getattr(message.author, "display_name", "") or getattr(message.author, "name", ""),
    )

    admin_ds = SUPPORT_ADMIN_DS or (AUTHORIZED_UPDATERS[0] if AUTHORIZED_UPDATERS else 0)
    if is_dm and admin_ds and user_id == admin_ds and message.reference is not None:
        tid = ticket_by_admin_message("ds", message.reference.message_id)
        if tid:
            ticket = get_ticket(tid) or {}
            append_ticket_message(tid, "support", message.content)
            if str(ticket.get("platform")) == "ds":
                target_id = int(ticket.get("user_id") or 0)
                try:
                    target = dcmd.ds_bot.get_user(target_id) or await dcmd.ds_bot.fetch_user(target_id)
                    await target.send(
                        f"💬 Пришёл ответ от поддержки по обращению №{tid}:\n\n{message.content}"
                    )
                    await message.reply(f"Ответ отправлен (обращение №{tid}).")
                except Exception as e:
                    await message.reply(f"Не смог отправить: {e}")
            return

    note_chat_participant(
        "ds", chat_id,
        getattr(message.author, "name", ""),
        getattr(message.author, "global_name", ""),
        getattr(message.author, "display_name", ""),
    )
    if guild is not None and guild.id not in _scanned_guilds:
        _scanned_guilds.add(guild.id)
        try:
            for _m in guild.members:
                note_chat_participant(
                    "ds", chat_id,
                    getattr(_m, "name", ""),
                    getattr(_m, "global_name", ""),
                    getattr(_m, "display_name", ""),
                )
        except Exception:
            pass
    content_lower = message.content.lower()
    display_name = str(getattr(message.author, "display_name", message.author.name))
    username = message.author.name
    cfg = get_effective_config("ds", chat_id, user_id)
    lang_raw = cfg.get("language", "ru")
    lang = lang_raw if isinstance(lang_raw, str) else "ru"

    # Ignore messages from this bot and unrelated bots to prevent self-conversation loops.
    if message.author.bot:
        if not await _is_addressed_from_bot_ds(message):
            return
        now = time.time()
        chat_key = f"ds_{chat_id}"
        if now - last_bot_reply.get(chat_key, 0) < 8:
            return
        last_bot_reply[chat_key] = now

    if not is_dm and (content_lower.startswith("кульш обновись") or content_lower.startswith("kulsh update")):
        if message.author.id not in AUTHORIZED_UPDATERS:
            await message.reply(tr(lang, "ds_update_no_access"))
            return
        await message.reply(tr(lang, "ds_update_start"))
        try:
            repo_path = os.getenv('REPO_PATH', os.getcwd())
            status, info = await perform_safe_git_update(repo_path)
            if status == "up_to_date":
                await message.reply(tr(lang, "ds_update_uptodate", info[:1500]))
            elif status == "ok":
                await message.reply(tr(lang, "ds_update_ok", info[:1500]))
                await asyncio.sleep(2)
                os._exit(0)
            elif status == "rolled_back":
                await message.reply(tr(lang, "ds_update_rolled", info[:1500]))
            else:
                await message.reply(tr(lang, "ds_update_error", info[:1500]))
        except Exception as e:
            logger.exception("update error")
            await message.reply(tr(lang, "ds_update_error", str(e)))
        return

    if (content_lower.startswith("кульш конфиг") or
            content_lower.startswith("кульш настройки") or
            content_lower.startswith("kulsh config")):
        parts = message.content.split()
        if len(parts) == 2:
            await ds_handle_config(message, user_id)
        else:
            await ds_handle_config_param(message, user_id, parts)
        return

    if content_lower.strip() in ("кульш статус", "kulsh status", "кульш состояние"):
        mode_raw = str(cfg.get("communication_mode", "kent"))
        if mode_raw == "assistant":
            mode_label = tr(lang, "mode_assistant")
        elif mode_raw == "pro":
            mode_label = tr(lang, "mode_pro")
        else:
            mode_label = tr(lang, "mode_kent")
        try:
            latency_ms = round(dcmd.ds_bot.latency * 1000)
        except Exception:
            latency_ms = 50
        from src.util import human_uptime, BOT_VERSION
        text = (
            f"# 🟢 {tr(lang, 'status_title')}\n\n**{tr(lang, 'status_online')}**\n\n"
            f"- {tr(lang, 'status_uptime')}: `{human_uptime()}`\n"
            f"- {tr(lang, 'status_latency')}: `~{latency_ms} ms`\n"
            f"- {tr(lang, 'status_mode')}: `{mode_label}`\n"
            f"- {tr(lang, 'status_mood')}: `{tr(lang, 'status_mood_value')}`\n\n"
            f"🍷🗿 · v{BOT_VERSION}"
        )
        await message.reply(text)
        return

    m = re.match(r'(?i)^(?:кульш\s+)?(?:поиск|search|найди|найти)\s+(.+)$', message.content.strip(), re.DOTALL)
    if m:
        if not cfg.get("web_search_enabled", True):
            await message.reply(tr(lang, "search_off"))
            return
        results = await search_with_anim_ds(message, m.group(1).strip())
        if not results:
            await message.reply(tr(lang, "search_nothing"))
            return
        last_search_sources[f"ds_{chat_id}"] = results
        context = format_search_results(results)
        prompt = (
            f"Пользователь просит поискать: {m.group(1).strip()}\n\nРезультаты:\n{context}\n\n"
            f"Ответь сам, живо и по делу. Ссылки вставлять не обязан, они у тебя в контексте."
        )
        answer = await ask_ai_async(prompt=prompt, chat_id=chat_id, user_id=user_id, platform="ds")
        segments, _markers = process_ai_response(
            answer or tr(lang, "search_nothing"),
            separate_enabled=cfg.get("separate_enabled", True),
        )
        for i, seg in enumerate(segments):
            seg = scrub_stray_markers(seg)
            if cfg.get("communication_mode", "kent") == "kent":
                seg = strip_chat_emojis(seg)
            if not seg:
                continue
            try:
                if i == 0:
                    await message.reply(seg[:1900])
                else:
                    await message.channel.send(seg[:1900])
            except Exception as e:
                logger.warning(f"ds search send: {e}")
        return

    m = re.match(r'(?i)^(?:кульш\s+)?(?:график|chart|инфографика|диаграмма)\s+(.+)$', message.content.strip(), re.DOTALL)
    if m:
        async with message.channel.typing():
            chart_prompt = (
                f"Сгенерируй JSON-спецификацию инфографики:\n\n{m.group(1).strip()}\n\n"
                f"Верни ТОЛЬКО JSON. Структура: {{theme, title, blocks}}"
            )
            raw = await ask_ai_async(
                prompt=chart_prompt,
                system_instruction_override="You are a data-viz JSON generator. Output only valid JSON.",
                chat_id=chat_id, user_id=user_id, platform="ds",
            )
            spec = None
            try:
                spec = json.loads(clean_json_text(raw))
            except Exception:
                mm = re.search(r'\{[\s\S]*\}', raw or "")
                if mm:
                    try:
                        spec = json.loads(mm.group(0))
                    except Exception:
                        spec = None
            if not isinstance(spec, dict):
                await message.reply(tr(lang, "chart_error", "invalid JSON"))
                return
            spec_dict = cast(JsonDict, spec)
            try:
                img = await render_infographic(spec_dict, user_images=None)
                await message.reply(file=discord.File(fp=img, filename="infographic.png"),
                                    content=(spec_dict.get("title") or tr(lang, "chart_built"))[:1900])
            except Exception as e:
                await message.reply(tr(lang, "chart_error", str(e)))
        return

    if content_lower.startswith("кульш донаты") or content_lower.startswith("kulsh donations"):
        top = get_top_donators()
        if not top:
            await message.reply(tr(lang, "top_donators_empty", DONATE_URL))
            return
        embed = discord.Embed(title=tr(lang, "top_donators_title"), color=0x10B981)
        for i, (name, total) in enumerate(top, 1):
            embed.add_field(name=f"{i}. {name}", value=f"{total}", inline=False)
        await message.reply(embed=embed)
        return

    if (content_lower.startswith("кульш аватарк") or content_lower.startswith("кульш аватар")
            or content_lower.startswith("kulsh avatar")):
        avatar_raw: str | None = await get_avatar_description_ds(message, chat_id, user_id, lang=str(lang))
        if not avatar_raw:
            await message.reply(tr(lang, "avatar_fail"))
            return
        for seg in clean_extra_text(avatar_raw):
            try:
                await message.channel.send(seg)
            except Exception as e:
                logger.warning(f"DS avatar: {e}")
        return

    if "кульш логи" in content_lower or "kulsh logs" in content_lower:
        if message.author.id not in AUTHORIZED_UPDATERS:
            await message.reply(tr(lang, "ds_update_no_access"))
            return
        try:
            tail = read_log_tail(20)
            intro = tr(lang, "ds_logs_content")
            try:
                await message.reply(
                    content=f"{intro}\n```\n{tail}\n```" if len(tail) <= 1900 else intro,
                    file=discord.File('bot.log'),
                )
            except FileNotFoundError:
                await message.reply(f"{intro}\n```\n{tail}\n```" if len(tail) <= 1900 else f"{intro}\n\n{tail}")
                return
            if len(tail) > 1900:
                for chunk in chunk_text(tail, 1900):
                    await message.channel.send(f"```\n{chunk}\n```")
        except Exception as e:
            await message.reply(f"Ошибка: {e}")
        return

    if not is_dm and ("кульш зайди в войс" in content_lower or "kulsh join voice" in content_lower):
        author = cast(discord.Member, message.author)
        if not (author.voice and author.voice.channel):
            await message.reply(tr(lang, "ds_voice_not_in"))
            return
        voice_channel = author.voice.channel
        if guild is None:
            return
        try:
            vc = voice_client(guild)
            if vc and vc.is_connected():
                await vc.move_to(voice_channel)
            else:
                if voice_recognition_enabled and voice_recv_available:
                    vc = cast(discord.VoiceClient, await voice_channel.connect(cls=voice_recv.VoiceRecvClient))
                else:
                    vc = await voice_channel.connect()
            voice_text_channels[guild.id] = message.channel
            await message.reply(tr(lang, "ds_voice_joined", voice_channel.name))
            if voice_recognition_enabled and voice_recv_available:
                sink = cast(Any, RecognitionSink)(dcmd.ds_bot, guild, message.channel)
                cast(Any, vc).listen(sink)
                setattr(vc, "_recognition_sink", sink)
        except Exception as e:
            logger.error(f"voice: {e}")
            await message.reply(tr(lang, "ds_voice_cant_join"))
        return

    if not is_dm and ("кульш выйди из войса" in content_lower or "kulsh leave voice" in content_lower):
        vc = voice_client(guild)
        if vc and vc.is_connected():
            if hasattr(vc, "_recognition_sink"):
                getattr(vc, "_recognition_sink").cleanup()
            await vc.disconnect()
            if guild is not None:
                voice_text_channels.pop(guild.id, None)
            await message.reply(tr(lang, "ds_voice_left"))
        else:
            await message.reply(tr(lang, "ds_voice_not_in_bot"))
        return

    if is_looksmaxxing_command(message.content) and len(message.attachments) == 0:
        add_user_memory(f"ds_{chat_id}", "DS", display_name, username, user_id, message.content, message_id=message.id)
        await message.reply(tr(lang, "psl_need_photo"))
        return

    if is_femboy_rate_command(message.content) and len(message.attachments) == 0:
        add_user_memory(f"ds_{chat_id}", "DS", display_name, username, user_id, message.content, message_id=message.id)
        await message.reply(tr(lang, "femboy_need_photo"))
        return

    if is_battle_command(message.content) and len(message.attachments) == 0:
        add_user_memory(f"ds_{chat_id}", "DS", display_name, username, user_id, message.content, message_id=message.id)
        await message.reply(tr(lang, "battle_need_photos"))
        return

    if is_femboy_battle_command(message.content) and len(message.attachments) == 0:
        add_user_memory(f"ds_{chat_id}", "DS", display_name, username, user_id, message.content, message_id=message.id)
        await message.reply(tr(lang, "femboy_battle_need_photos"))
        return

    image_attachments = [a for a in message.attachments if a.content_type and a.content_type.startswith('image/')]
    video_attachments = [a for a in message.attachments if a.content_type and a.content_type.startswith('video/')]
    has_battle_cmd = is_battle_command(message.content)
    has_femboy_battle = is_femboy_battle_command(message.content)

    if has_battle_cmd and len(image_attachments) >= 2:
        async with message.channel.typing():
            status_msg = await message.reply(tr(lang, "battle_waiting"))
            try:
                p1 = await download_image_bytes(image_attachments[0].url)
                p2 = await download_image_bytes(image_attachments[1].url)
                theme = cfg.get("theme", "dark")
                ai_data = await get_battle_data(p1, p2, lang=lang)
                if "error" in ai_data:
                    await status_msg.edit(content=str(ai_data['error']))
                    return
                img = await create_battle_infographic(p1, p2, ai_data, theme=theme, lang=lang)
                winner_num = str(ai_data.get("winner", "1"))
                winner_label = tr(lang, "battle_first") if winner_num == "1" else tr(lang, "battle_second")
                report = (
                    f"**{tr(lang, 'battle_title')}**\n\n"
                    f"{tr(lang, 'battle_winner')} **{winner_label}**\n"
                    f"{tr(lang, 'battle_reason')} {ai_data.get('reason', '')}"
                )
                await message.reply(file=discord.File(fp=img, filename="battle.png"), content=report[:1900])
                await status_msg.delete()
            except Exception as e:
                logger.error(f"DS battle: {e}")
                await status_msg.edit(content=f"Ошибка: {e}")
        return

    if has_femboy_battle and len(image_attachments) >= 2:
        async with message.channel.typing():
            status_msg = await message.reply(tr(lang, "femboy_battle_waiting"))
            try:
                p1 = await download_image_bytes(image_attachments[0].url)
                p2 = await download_image_bytes(image_attachments[1].url)
                theme = cfg.get("theme", "dark")
                ai_data = await get_femboy_battle_data(p1, p2, lang=lang)
                if "error" in ai_data:
                    await status_msg.edit(content=str(ai_data['error']))
                    return
                img = await create_femboy_battle_infographic(p1, p2, ai_data, theme=theme, lang=lang)
                winner_num = str(ai_data.get("winner", "1"))
                winner_label = tr(lang, "femboy_battle_first") if winner_num == "1" else tr(lang, "femboy_battle_second")
                report = (
                    f"**{tr(lang, 'femboy_battle_title')}**\n\n"
                    f"{tr(lang, 'femboy_battle_winner')} **{winner_label}**"
                )
                await message.reply(file=discord.File(fp=img, filename="femboy_battle.png"), content=report[:1900])
                await status_msg.delete()
            except Exception as e:
                logger.error(f"DS femboy battle: {e}")
                await status_msg.edit(content=f"Ошибка: {e}")
        return

    has_looksmaxxing_cmd = is_looksmaxxing_command(message.content)
    has_femboy_cmd = is_femboy_rate_command(message.content)

    if has_looksmaxxing_cmd and len(image_attachments) > 0:
        async with message.channel.typing():
            try:
                psl_bytes = await download_image_bytes(image_attachments[0].url)
                include_advice = "совет" in content_lower or "advice" in content_lower
                theme = cfg.get("theme", "dark")
                ai_data = await get_looksmaxxing_data(
                    psl_bytes, include_advice, lang=lang, chat_id=chat_id, user_id=user_id, platform="ds",
                )
                if ai_data.get("not_a_face"):
                    await message.reply(ai_data.get("message", tr(lang, "psl_not_a_face")))
                    return
                if "error" in ai_data:
                    await message.reply(ai_data['error'])
                    return
                infographic = await create_infographic(psl_bytes, ai_data, theme=theme, lang=lang)
                report = (
                    f"**{tr(lang, 'psl_title')}**\n"
                    f"{tr(lang, 'psl_gender')} {ai_data.get('gender', '?')}\n"
                    f"{tr(lang, 'psl_score')} `{ai_data.get('psl', '?')}/8.0`\n"
                    f"{tr(lang, 'psl_tier')} `{ai_data.get('tier', '?')}`"
                )
                await message.reply(file=discord.File(fp=infographic, filename="psl.png"), content=report[:1900])
            except Exception as e:
                logger.error(f"DS looksmaxxing: {e}")
                await message.reply(f"Ошибка: {e}")
        return

    if has_femboy_cmd and len(image_attachments) > 0:
        async with message.channel.typing():
            try:
                img_bytes = await download_image_bytes(image_attachments[0].url)
                include_advice = "совет" in content_lower or "advice" in content_lower
                theme = cfg.get("theme", "dark")
                ai_data = await get_femboy_data(img_bytes, include_advice, lang=lang)
                if "error" in ai_data:
                    await message.reply(ai_data['error'])
                    return
                infographic = await create_femboy_infographic(img_bytes, ai_data, theme=theme, lang=lang)
                report = (
                    f"**{tr(lang, 'femboy_title')}**\n"
                    f"{tr(lang, 'femboy_gender')} {ai_data.get('gender', '?')}\n"
                    f"{tr(lang, 'femboy_score')} `{ai_data.get('fmb', '?')}/10.0`"
                )
                await message.reply(file=discord.File(fp=infographic, filename="femboy.png"), content=report[:1900])
            except Exception as e:
                logger.error(f"DS femboy: {e}")
                await message.reply(f"Ошибка: {e}")
        return

    for att in image_attachments:
        add_media_history(f"ds_{chat_id}", att.url, "photo", display_name,
                          caption=message.content[:200], message_id=message.id)
    for att in video_attachments:
        add_media_history(f"ds_{chat_id}", att.url, "video", display_name,
                          caption=message.content[:200], message_id=message.id)

    is_reply_to_bot = False
    if message.reference and message.reference.resolved and isinstance(message.reference.resolved, discord.Message):
        if message.reference.resolved.author == dcmd.ds_bot.user:
            is_reply_to_bot = True

    addressed = bool(is_reply_to_bot or re.search(r'(?i)\bкульш\b', message.content) or is_dm
                     or (message.author.bot and await _is_addressed_from_bot_ds(message)))

    if (image_attachments or video_attachments) and addressed:
        async with message.channel.typing():
            try:
                media_bytes: bytes | None = None
                img_mime = "image/jpeg"
                if image_attachments:
                    media_bytes = await download_image_bytes(image_attachments[0].url)
                    img_mime = image_attachments[0].content_type or "image/jpeg"
                elif video_attachments:
                    vid = await download_image_bytes(video_attachments[0].url)
                    frame = await extract_video_frame(vid, ".mp4")
                    if frame:
                        media_bytes = frame
                prompt = message.content.strip() or ""
                add_user_memory(f"ds_{chat_id}", "DS", display_name, username, user_id,
                                f"{prompt or '[медиа без подписи]'} [с медиа]",
                                ["photo" if image_attachments else "video"],
                                message_id=message.id)
                messages = memory_to_messages(get_chat_memory(f"ds_{chat_id}"))
                answer = await ask_ai_async(messages=messages, image_bytes=media_bytes,
                                            image_mime=img_mime, chat_id=chat_id,
                                            user_id=user_id, platform="ds")
                await send_ds_ai_response(message, chat_id, user_id, answer, user_text=prompt)
                asyncio.create_task(extract_memory(f"ds_{chat_id}", f"{display_name}: [медиа]", answer,
                                                   platform="ds", user_id=user_id, source_chat_id=chat_id))
            except Exception as e:
                logger.info(f"DS media: {e}")
                await message.reply(tr(lang, "ds_attachments_error"))
        return

    if addressed:
        async with message.channel.typing():
            add_user_memory(f"ds_{chat_id}", "DS", display_name, username, user_id,
                            message.content, message_id=message.id)
            messages = memory_to_messages(get_chat_memory(f"ds_{chat_id}"))
            answer = await ask_ai_async(messages=messages, chat_id=chat_id,
                                        user_id=user_id, platform="ds")
            await send_ds_ai_response(message, chat_id, user_id, answer, user_text=message.content)
            asyncio.create_task(extract_memory(f"ds_{chat_id}", f"{display_name}: {message.content}", answer,
                                               platform="ds", user_id=user_id, source_chat_id=chat_id))
        return

    add_user_memory(f"ds_{chat_id}", "DS", display_name, username, user_id, message.content, message_id=message.id)
    if not message.author.bot and await should_random_reply("ds", chat_id, user_id):
        try:
            answer = await ask_ai_async(
                context_type="observer",
                messages=memory_to_messages(get_chat_memory(f"ds_{chat_id}")),
                chat_id=chat_id, user_id=user_id, platform="ds",
            )
            if (answer and answer.strip() and answer.strip().upper() not in ("НЕТ", "NO")
                    and not message.author.bot):
                last_random_reply[f"ds_{chat_id}"] = time.time()
                await send_ds_ai_response(message, chat_id, user_id, answer)
        except Exception as e:
            logger.warning(f"DS random reply: {e}")


if voice_recognition_enabled and voice_recv_available:
    class RecognitionSink(voice_recv.AudioSink):  # type: ignore[misc]
        def __init__(self, bot: discord.Client, guild: discord.Guild, text_channel: discord.abc.Messageable) -> None:
            super().__init__()  # pyright: ignore[reportUnknownMemberType]
            self.bot = bot
            self.guild = guild
            self.text_channel = text_channel
            self.buffers: dict[int | str, bytearray] = {}
            self.recognizer = sr.Recognizer()
            self.processing_tasks: dict[int | str, Any] = {}

        def wants_opus(self) -> bool:
            return False

        def write(self, user: discord.User | None, data: Any) -> None:
            user_id = user.id if user else "unknown_session"
            user_name = user.name if user else "Аноним"
            if user and user.bot:
                return
            if user_id not in self.buffers:
                self.buffers[user_id] = bytearray()
            self.buffers[user_id].extend(cast(bytes, data.pcm))
            if len(self.buffers[user_id]) > 380000:
                if user_id in self.processing_tasks:
                    self.processing_tasks[user_id].cancel()
                self.processing_tasks[user_id] = asyncio.run_coroutine_threadsafe(
                    self.wait_and_process(user_id, user_name), self.bot.loop
                )

        def _sync_recognize(self, pcm_data: bytes) -> str | None:
            try:
                audio = AudioSegment(data=pcm_data, sample_width=2, frame_rate=48000,
                                     channels=2).set_channels(1).set_frame_rate(16000)
                wav_io = BytesIO()
                audio.export(wav_io, format="wav")
                wav_io.seek(0)
                with sr.AudioFile(wav_io) as source:
                    recognized = self.recognizer.recognize_google(
                        self.recognizer.record(source), language="ru-RU"
                    )
                    return recognized if isinstance(recognized, str) else None
            except sr.UnknownValueError:
                return None
            except Exception as e:
                logger.error(f"recognize: {e}")
                return None

        async def wait_and_process(self, user_id: int | str, user_name: str) -> None:
            try:
                await asyncio.sleep(1.5)
                if user_id in self.buffers:
                    pcm_data = bytes(self.buffers.pop(user_id))
                    text = await asyncio.to_thread(self._sync_recognize, pcm_data)
                    if text and random.random() <= 0.65:
                        logger.info(f"🎤 Распознано: {text}")
            except asyncio.CancelledError:
                pass

        def cleanup(self) -> None:
            for task in self.processing_tasks.values():
                task.cancel()
            self.buffers.clear()
else:
    class RecognitionSink:  # type: ignore[no-redef]
        pass
