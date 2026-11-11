# Kulsh GPT | v2.48.0
# by (main author): starf6ll
# coauthor & bot hosting: pomidorka1515

"""Background loops: random posts, series reminders, donations, TTS, config save."""

import asyncio
import random
import time
from typing import Any, cast

import discord
import socketio

from src.ai import ask_ai_async
from src.rich import send_tg_html
from src import agent
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
    get_user_config,
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
_last_autonomous: dict[str, float] = {}
AUTONOMOUS_COOLDOWN = 7200


async def _autonomous_candidates(platform: str) -> list[dict[str, Any]]:
    """Все группы и каналы, где бот имеет право писать сам.

    В личке автономных сообщений нет вообще — только группы и серверы.
    """
    from src import chats
    found: list[dict[str, Any]] = []
    for entry in chats.all_chats():
        if entry.get("platform") != platform:
            continue
        if entry.get("kind") not in ("group", "channel"):
            continue
        chat_id = int(entry.get("id") or 0)
        if not chat_id:
            continue
        if not get_user_config(platform, chat_id, int(entry.get("owner_id") or 0)).get(
                "random_messages_enabled", True):
            continue
        found.append(entry)
    # Старый random_post_loop всегда писал в TG_TARGET_CHAT. Если после
    # рестарта бот ещё не получал там сообщений, реестр пуст — добавляем
    # этот чат, чтобы автономные сообщения не пропадали.
    if platform == "tg" and TG_TARGET_CHAT < 0:
        known = {int(entry.get("id") or 0) for entry in found}
        if TG_TARGET_CHAT not in known:
            found.append({"platform": "tg", "id": TG_TARGET_CHAT, "kind": "group",
                          "title": str(TG_TARGET_CHAT), "owner_id": 0})
    return found


async def _autonomous_post(platform: str, chat_id: int, user_id: int = 0) -> None:
    """Одна самостоятельная реплика бота в конкретном чате.

    Это ровно старая логика до межчатовых сообщений: если в чате есть
    история — бот смотрит на неё и решает, что добавить; если истории нет —
    пишет спонтанную реплику. Кто написал последним и когда, не проверяется.
    """
    from src import chats
    if not chats.is_group(platform, chat_id):
        return
    chat_key = f"{platform}_{chat_id}"
    memory = get_chat_memory(chat_key)
    try:
        if memory:
            answer = await ask_ai_async(
                prompt=("Посмотри на историю чата. Если хочешь что-то добавить или пошутить, напиши одно "
                        "короткое сообщение. Если нет — ответь ровно 'НЕТ'."),
                context_type="observer",
                messages=memory_to_messages(memory),
                chat_id=chat_id, user_id=user_id, platform=platform,
            )
        else:
            answer = await ask_ai_async(
                prompt=None, context_type="random",
                chat_id=chat_id, user_id=user_id, platform=platform,
            )
    except Exception as exc:
        logger.info(f"autonomous ask {chat_key}: {exc}")
        return
    if not answer or not answer.strip() or answer.strip().upper() in ("НЕТ", "NO"):
        return
    segments, markers = process_ai_response(answer, separate_enabled=True)
    if not segments:
        return
    clean = [strip_chat_emojis(scrub_stray_markers(seg)).strip() for seg in segments]
    clean = [seg for seg in clean if seg]
    if not clean:
        return
    await agent.deliver_message(platform, chat_id, answer, user_id=0, clean_style=True)
    for seg in clean:
        add_bot_memory(chat_key, seg)
    for marker_name in markers:
        if marker_name == "sticker" and platform == "tg":
            try:
                await tg_bot.send_sticker(chat_id, random.choice(STICKER_POOL))
            except Exception as exc:
                logger.warning(f"autonomous sticker {chat_key}: {exc}")
        elif marker_name.startswith("tell:"):
            try:
                query, outgoing = marker_name[5:].split("\x1f", 1)
                result = await agent.tell(platform, chat_id, False, 0, query, outgoing)
                report = await agent.describe_tell(platform, chat_id, 0, result)
                if report:
                    await agent._send_text(platform, chat_id, report)
            except Exception as exc:
                logger.warning(f"autonomous tell {chat_key}: {exc}")
        elif marker_name.startswith("notify_owner:"):
            try:
                await agent.notify_owner(
                    f"⚠️ Самостоятельное сообщение в {chat_key}: {marker_name.split(':', 1)[1].strip()}",
                    source=f"notice:{chat_key}",
                )
            except Exception as exc:
                logger.warning(f"autonomous notify {chat_key}: {exc}")


async def random_post_loop() -> None:
    """Самостоятельные сообщения во всех группах Telegram, где бот состоит."""
    while True:
        await asyncio.sleep(random.randint(3600, 14400))
        try:
            candidates = await _autonomous_candidates("tg")
            random.shuffle(candidates)
            for entry in candidates:
                chat_id = int(entry.get("id") or 0)
                if time.time() - _last_autonomous.get(f"tg_{chat_id}", 0) < AUTONOMOUS_COOLDOWN:
                    continue
                _last_autonomous[f"tg_{chat_id}"] = time.time()
                await _autonomous_post("tg", chat_id, int(entry.get("owner_id") or 0))
        except Exception as exc:
            logger.info(f"random_post_loop: {exc}")


async def ds_autonomous_loop() -> None:
    """Самостоятельные сообщения во всех каналах Discord, где бот на сервере."""
    if ds_bot is None:
        return
    try:
        await ds_bot.wait_until_ready()
    except Exception:
        pass
    try:
        from src import chats
        for guild in getattr(ds_bot, "guilds", []) or []:
            target = getattr(guild, "system_channel", None)
            if target is None:
                for channel in list(getattr(guild, "text_channels", []) or [])[:10]:
                    try:
                        if channel.permissions_for(guild.me).send_messages:
                            target = channel
                            break
                    except Exception:
                        continue
            if target is not None:
                chats.register("ds", target.id, "channel", guild.name, guild.id)
    except Exception as exc:
        logger.info(f"ds_autonomous seed: {exc}")
    while True:
        await asyncio.sleep(random.randint(3600, 14400))
        try:
            candidates = await _autonomous_candidates("ds")
            random.shuffle(candidates)
            for entry in candidates:
                chat_id = int(entry.get("id") or 0)
                if time.time() - _last_autonomous.get(f"ds_{chat_id}", 0) < AUTONOMOUS_COOLDOWN:
                    continue
                _last_autonomous[f"ds_{chat_id}"] = time.time()
                await _autonomous_post("ds", chat_id, int(entry.get("owner_id") or 0))
        except Exception as exc:
            logger.info(f"ds_autonomous_loop: {exc}")


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
