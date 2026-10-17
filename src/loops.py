# Kulsh GPT | v2.48.0
# by (main author): starfall-apk
# coauthor & bot hosting: pomidorka1515

"""Background loops: random posts, series reminders, donations, TTS, config save."""

import asyncio
import random
from typing import Any, cast

import discord
import socketio

from src.ai import ask_ai_async
from src.rich import send_tg_html
from src.util import (
    STICKER_POOL,
    DONATIONALERTS_TOKEN,
    DS_DONATION_CHANNEL_ID,
    DS_SERIES_CHANNEL_ID,
    DS_SERIES_TARGET_USER_ID,
    TG_TARGET_CHAT,
    voice_enabled,
    messageable,
    add_bot_memory,
    add_donation,
    edge_tts,
    get_chat_memory,
    logger,
    memory_to_messages,
    process_ai_response,
    save_user_configs,
    scrub_stray_markers,
    strip_chat_emojis,
    JsonDict,
)

ds_bot: Any = None
tg_bot: Any = None


def bind(discord_bot: Any, telegram_bot: Any) -> None:
    global ds_bot, tg_bot
    ds_bot = discord_bot
    tg_bot = telegram_bot


async def send_donation_alert(platform: str, name: str, amount: int, message_text: str = '') -> None:
    if platform == 'tg':
        text = f"🍷🗿 {name} задонатил {amount} звёзд! Спасибо!"
        if message_text:
            text += f"\nСообщение: {message_text}"
        try:
            await send_tg_html(TG_TARGET_CHAT, text)
        except Exception as e:
            logger.error(f"Донат в ТГ: {e}")
    elif platform == 'ds':
        text = f"💎 {name} задонатил {amount} руб."
        if message_text:
            text += f"\n> {message_text}"
        if DS_DONATION_CHANNEL_ID:
            channel = ds_bot.get_channel(DS_DONATION_CHANNEL_ID)
            sendable = messageable(cast(discord.abc.Messageable | None, channel))
            if sendable is not None:
                try:
                    await sendable.send(text)
                except Exception as e:
                    logger.error(f"Донат в DS: {e}")


async def donation_alerts_listener() -> None:
    if not DONATIONALERTS_TOKEN:
        logger.info("🔕 DonationAlerts токен не задан.")
        return
    await ds_bot.wait_until_ready()
    sio = socketio.AsyncClient()

    @sio.event
    async def connect() -> None:
        logger.info("🔌 DonationAlerts подключён")

    @sio.event
    async def disconnect() -> None:
        logger.warning("🔌 DonationAlerts отключён")

    @sio.on('donation')
    async def on_donation(data: JsonDict) -> None:
        try:
            amount = float(data.get('amount', 0))
            currency = str(data.get('currency', 'RUB'))
            if currency != 'RUB':
                return
            points = int(amount)
            username = str(data.get('username', 'Аноним'))
            message = str(data.get('message', ''))
            logger.info(f"💰 {username} → {points}")
            add_donation('ds', 0, points, name=username)
            await send_donation_alert('ds', username, points, message)
        except Exception as e:
            logger.error(f"DA error: {e}")

    try:
        await sio.connect(
            f'https://socket.donationalerts.ru:443?token={DONATIONALERTS_TOKEN}',
            transports=['websocket'],
        )
        await sio.wait()
    except Exception as e:
        logger.error(f"DA connect fail: {e}")


async def say_in_voice(voice_client: discord.VoiceClient | None, text: str) -> None:
    if not voice_enabled or not voice_client or not voice_client.is_connected():
        return
    try:
        filename = f"temp_voice_{voice_client.guild.id}.mp3"
        communicate = edge_tts.Communicate(text, "uk-UA-OstapNeural")
        await communicate.save(filename)
        if voice_client.is_playing():
            voice_client.stop()
        voice_client.play(discord.FFmpegPCMAudio(filename))
    except Exception as e:
        logger.error(f"TTS: {e}")


# ============================================================
# ПЕРИОДИЧЕСКОЕ СОХРАНЕНИЕ НАСТРОЕК
# ============================================================
async def periodic_config_save_loop() -> None:
    """Каждые 60 секунд сохраняет настройки пользователей на диск."""
    while True:
        await asyncio.sleep(60)
        try:
            save_user_configs()
        except Exception as e:
            logger.warning(f"periodic_config_save_loop: {e}")


# ============================================================
# ОСНОВНЫЕ ЦИКЛЫ
# ============================================================
async def random_post_loop() -> None:
    while True:
        await asyncio.sleep(random.randint(3600, 14400))
        chat_key = f"tg_{TG_TARGET_CHAT}"
        memory = get_chat_memory(chat_key)
        try:
            if memory:
                answer = await ask_ai_async(
                    prompt=("Посмотри на историю чата. Если хочешь что-то добавить или пошутить, напиши одно "
                            "короткое сообщение. Если нет — ответь ровно 'НЕТ'."),
                    context_type="observer",
                    messages=memory_to_messages(memory),
                    chat_id=TG_TARGET_CHAT, user_id=0, platform="tg",
                )
            else:
                answer = await ask_ai_async(prompt=None, context_type="random",
                                            chat_id=TG_TARGET_CHAT, user_id=0, platform="tg")
            if not answer or not answer.strip() or answer.strip().upper() in ("НЕТ", "NO"):
                continue
            segments, markers = process_ai_response(answer, separate_enabled=True)
            for seg in segments:
                seg = scrub_stray_markers(seg)
                seg = strip_chat_emojis(seg)
                if not seg:
                    continue
                await send_tg_html(TG_TARGET_CHAT, seg)
                add_bot_memory(chat_key, seg)
            for m in markers:
                if m == "sticker":
                    try:
                        await tg_bot.send_sticker(TG_TARGET_CHAT, random.choice(STICKER_POOL))
                    except Exception as e:
                        logger.warning(f"random_post sticker: {e}")
        except Exception as e:
            logger.info(f"random_post_loop: {e}")


async def series_reminder_loop() -> None:
    await ds_bot.wait_until_ready()
    channel = cast(discord.TextChannel, ds_bot.get_channel(DS_SERIES_CHANNEL_ID))
    if not channel:
        logger.error("Канал серии не найден")
        return
    while True:
        try:
            prompt = ("Напиши Антону короткое напоминание про фолзу в тикток, чтобы не сгорела серия. "
                      "Одна живая реплика как кент в нашем чате: строчными буквами, без приветствия, "
                      "без вежливого официоза, без примера готового сообщения для пересылки и без эмодзи. "
                      "Не объясняй задачу, просто напиши само напоминание.")
            answer = await ask_ai_async(prompt=prompt, context_type="default",
                                        chat_id=DS_SERIES_CHANNEL_ID, user_id=0, platform="ds")
            segments, _ = process_ai_response(answer, separate_enabled=True)
            if segments:
                first = strip_chat_emojis(scrub_stray_markers(segments[0]))
                if first:
                    await channel.send(f"<@{DS_SERIES_TARGET_USER_ID}> {first}")
                for seg in segments[1:]:
                    seg = strip_chat_emojis(scrub_stray_markers(seg))
                    if seg:
                        await channel.send(seg)
        except Exception as e:
            logger.error(f"series_reminder_loop: {e}")
        await asyncio.sleep(86400)