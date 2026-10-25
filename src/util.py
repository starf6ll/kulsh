# Kulsh GPT | v2.49.0
# by (main author): starfall-apk
# coauthor & bot hosting: pomidorka1515

"""Shared helpers: time, i18n, typing, persistence, memory, text, media bytes."""

import asyncio
import base64
import datetime
import html
import json
import logging
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import defaultdict, deque
from datetime import timedelta, timezone
from logging.handlers import RotatingFileHandler
from typing import Any, Callable, Protocol, TypeAlias, TypeVar, cast

import aiohttp
import discord
from telebot import types as types
from dotenv import load_dotenv
from PIL import ImageFont
from telebot.async_telebot import AsyncTeleBot

# ============================================================
# ПУТИ К ДАННЫМ
# ------------------------------------------------------------
# Все файлы состояния живут в BASE_DIR/data/, чтобы git pull и
# git reset --hard не затирали пользовательские настройки.
# DATA_DIR автоматически добавляется в .gitignore.
# ============================================================
BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR: str = os.path.join(BASE_DIR, "data")
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except Exception:
    DATA_DIR = os.getcwd()

BOT_LOG_FILE: str = os.path.join(DATA_DIR, "bot.log")
DONATIONS_FILE: str = os.path.join(DATA_DIR, "donations.json")
MEMORY_FILE: str = os.path.join(DATA_DIR, "long_term_memory.json")
CREDITS_FILE: str = os.path.join(DATA_DIR, "credits.json")
USER_CONFIGS_FILE: str = os.path.join(DATA_DIR, "user_configs.json")
DS_SCOPES_FILE: str = os.path.join(DATA_DIR, "ds_scopes.json")
TRUSTED_CHATS_FILE: str = os.path.join(DATA_DIR, "trusted_chats.json")
PREMIUM_STATE_FILE: str = os.path.join(DATA_DIR, "premium.json")
BALANCES_FILE: str = os.path.join(DATA_DIR, "balances.json")
DA_PROCESSED_FILE: str = os.path.join(DATA_DIR, "da_processed.json")
TICKETS_FILE: str = os.path.join(DATA_DIR, "support_tickets.json")
DA_TOKEN_FILE: str = os.path.join(DATA_DIR, "da_token.json")
PROMO_FILE: str = os.path.join(DATA_DIR, "promocodes.json")
ADMIN_USERS_FILE: str = os.path.join(DATA_DIR, "admin_users.json")
BLOCK_FILE: str = os.path.join(DATA_DIR, "blocked_users.json")
ADMIN_REQUESTS_FILE: str = os.path.join(DATA_DIR, "request_log.json")
CLOUD_MIGRATED_FILE: str = os.path.join(DATA_DIR, "cloud_migrated.json")

# ============================================================
# ЛОГГЕР
# ============================================================
logger = logging.getLogger('KulshBot')
logger.setLevel(logging.DEBUG)
log_formatter = logging.Formatter(
    '%(asctime)s | %(levelname)-7s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
try:
    file_handler = RotatingFileHandler(BOT_LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=1, encoding='utf-8')
    file_handler.setFormatter(log_formatter)
    logger.addHandler(file_handler)
except Exception:
    pass
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

BOT_START_TS: float = time.time()
BOT_VERSION: str = "2.51.0"

MSK = timezone(timedelta(hours=3))


def msk_now() -> datetime.datetime:
    return datetime.datetime.now(MSK)


def msk_time_str() -> str:
    return msk_now().strftime('%H:%M')


def msk_datetime_str() -> str:
    return msk_now().strftime('%d.%m.%Y %H:%M:%S МСК')


WEEKDAYS_RU = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")


def msk_human_now() -> str:
    """Текущее московское время в человекочитаемом виде с днём недели."""
    now = msk_now()
    return f"{now.strftime('%H:%M')} ({WEEKDAYS_RU[now.weekday()]}, {now.strftime('%d.%m.%Y')}) МСК"


def humanize_age(seconds: float) -> str:
    """«5 минут назад», «3 часа назад», «2 дня назад»."""
    seconds = max(0.0, seconds)
    if seconds < 90:
        return "только что"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} мин назад"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} ч назад"
    days = hours // 24
    return f"{days} дн назад"


def human_uptime() -> str:
    secs = int(time.time() - BOT_START_TS)
    d, secs = divmod(secs, 86400)
    h, secs = divmod(secs, 3600)
    m, secs = divmod(secs, 60)
    parts: list[str] = []
    if d:
        parts.append(f"{d}д")
    if h or d:
        parts.append(f"{h}ч")
    parts.append(f"{m}м")
    return " ".join(parts)


# ============================================================
# GITIGNORE
# ------------------------------------------------------------
# При первом запуске дописываем data/ в .gitignore, чтобы JSON-файлы
# состояния не попали в репо и не затирались при git pull / reset.
# ============================================================
def _ensure_gitignore() -> None:
    gi = os.path.join(BASE_DIR, ".gitignore")
    needed = ["data/", "*.log", "__pycache__/", "*.pyc", ".venv/", "venv/"]
    try:
        existing = ""
        if os.path.isfile(gi):
            with open(gi, encoding="utf-8") as f:
                existing = f.read()
        lines = set(line.strip() for line in existing.splitlines())
        missing = [n for n in needed if n not in lines]
        if missing:
            with open(gi, "a", encoding="utf-8") as f:
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                for line in missing:
                    f.write(line + "\n")
            logger.info(f".gitignore: добавлено {missing}")
    except Exception as e:
        logger.warning(f"_ensure_gitignore: {e}")


try:
    _ensure_gitignore()
except Exception:
    pass


load_dotenv()
TG_TOKEN: str = os.getenv('TG_TOKEN') or ""
DISCORD_TOKEN: str = os.getenv('DISCORD_TOKEN') or ""
AI_KEY = os.getenv('AI_KEY')
AI_KEY_1 = os.getenv('AI_KEY_1')
AI_KEY_2 = os.getenv('AI_KEY_2')
AI_KEY_3 = os.getenv('AI_KEY_3')
ETAGEONE_API_KEY: str = os.getenv('ETAGEONE_API_KEY') or ""
ETAGEONE_URL = "https://api.etage.one/v1/chat/completions"
TG_TARGET_CHAT = int(os.getenv('TG_TARGET_CHAT') or "0")
DS_ALLOWED_GUILD_ID = int(os.getenv('DS_ALLOWED_GUILD_ID') or "0")
DS_DONATION_CHANNEL_ID = int(os.getenv('DONATIONALERTS_CHANNEL_ID', '0'))
DONATIONALERTS_TOKEN = os.getenv('DONATIONALERTS_TOKEN', '')

AI_KEYS = [k for k in [AI_KEY_1, AI_KEY_2, AI_KEY_3] if k]
if not AI_KEYS and AI_KEY:
    AI_KEYS.append(AI_KEY)

DS_SERIES_GUILD_ID = 1403828466075304036
DS_SERIES_CHANNEL_ID = 1403828467014832270
DS_SERIES_TARGET_USER_ID = 1364588699589021890

# Чаты, где Кульшу разрешено говорить о своих кентах.
# Правило: если в чате есть хотя бы один кент — можно. Плюс два исторических чата.
TRUSTED_TG_CHAT_ID = 2413532783
TRUSTED_DS_GUILD_ID = 1403828466075304036
trusted_ds_channels: set[int] = set()

# Алиасы кентов в нижнем регистре. Используются, чтобы понять, что кент есть в чате.
KENT_ALIASES: tuple[str, ...] = (
    "фоллз", "фолз", "starfall-apk", "starfall", "lolfall",
    "рекми", "реким", "reqim", "rekme",
    "нейзи", "neizy", "n3iz", "n3", "н3",
    "ponil", "понил",
    "kwinic", "чмо",
)
_KENT_RE = re.compile(
    r'(?<![a-zа-яё0-9])(?:' + "|".join(re.escape(a) for a in KENT_ALIASES) + r')(?![a-zа-яё0-9])',
    re.IGNORECASE,
)

trusted_chats: dict[str, bool] = {}
try:
    if os.path.isfile(TRUSTED_CHATS_FILE):
        with open(TRUSTED_CHATS_FILE, encoding='utf-8') as _f:
            trusted_chats = {str(k): bool(v) for k, v in json.load(_f).items()}
except Exception:
    trusted_chats = {}


def _save_trusted_chats() -> None:
    try:
        with open(TRUSTED_CHATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(trusted_chats, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"trusted_chats save fail: {e}")


def mark_trusted_chat(platform: str, chat_id: int) -> None:
    key = f"{platform}_{chat_id}"
    if not trusted_chats.get(key):
        trusted_chats[key] = True
        _save_trusted_chats()


def note_chat_participant(platform: str, chat_id: int, *names: str | None) -> None:
    """Если среди участников засветился ник кента — помечаем чат доверенным."""
    joined = " ".join(n for n in names if n)
    if joined and _KENT_RE.search(joined):
        mark_trusted_chat(platform, chat_id)


def register_ds_channel(chat_id: int, guild_id: int | None) -> None:
    """Запоминает каналы «доверенного» сервера, чтобы промпт мог это учитывать."""
    if guild_id == TRUSTED_DS_GUILD_ID:
        trusted_ds_channels.add(chat_id)
        mark_trusted_chat("ds", chat_id)


def is_trusted_chat(platform: str, chat_id: int) -> bool:
    if platform == "tg" and chat_id == TRUSTED_TG_CHAT_ID:
        return True
    if platform == "ds" and chat_id in trusted_ds_channels:
        return True
    return bool(trusted_chats.get(f"{platform}_{chat_id}"))

MINI_APP_URL = "https://kulsh.vercel.app"
DONATE_URL = "https://kulsh.vercel.app/donate"
GITHUB_URL = "https://github.com/starfall-apk/kulsh"

ETAGEONE_MODELS = (
    "glm-5.3-flash",
    "deepseek-v4.1-flash",
    "kimi-k3",
    "deepseek-v4-pro",
    "gpt-6-luna",
    "claude-haiku-5-5",
    "gpt-6.1-sol",
    "gpt-6-astra",
    "grok-4.7",
    "claude-fable-5-1",
    "claude-opus-5-5",
    "claude-sonnet-5-5",
    "qwen3.8-max-0902",
)
GEMINI_MODELS = (
    "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash",
    "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
)

# Порядок компаний в меню. Внутри — от сильных к дешёвым.
MODEL_GROUPS: list[tuple[str, list[str]]] = [
    ("Anthropic", ["claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1", "claude-haiku-5-5"]),
    ("DeepSeek", ["deepseek-v4-pro", "deepseek-v4.1-flash"]),
    ("Google DeepMind", list(GEMINI_MODELS)),
    ("Moonshot AI", ["kimi-k3"]),
    ("OpenAI", ["gpt-6.1-sol", "gpt-6-astra", "gpt-6-luna"]),
    ("Z.AI", ["glm-5.3-flash"]),
    ("xAI", ["grok-4.7"]),
    ("Alibaba", ["qwen3.8-max-0902"]),
]

MODEL_GROUPS = [(company, [m for m in models if m]) for company, models in MODEL_GROUPS]
MODEL_GROUPS = [(company, models) for company, models in MODEL_GROUPS if models]

MODEL_LIST = [m for _company, _models in MODEL_GROUPS for m in _models]

# ============================================================
# АВТО-ПОРЯДОК МОДЕЛЕЙ (когда пользователь не выбрал конкретную)
# ------------------------------------------------------------
# Логика: сначала быстрые дешёвые чат-модели, потом остальные
# бесплатные, потом Gemini 2.5 (в конце бесплатных), потом
# DeepSeek V4 Pro (самая тяжёлая бесплатная, но БЕЗ vision),
# и только затем платные по возрастанию цены.
# NO_VISION_MODELS не пробуем, если в запросе есть картинка.
# ============================================================
AUTO_ORDER_FREE: list[str] = [
    "glm-5.3-flash",
    "deepseek-v4.1-flash",
    "kimi-k3",
    "gpt-6-luna",
    "claude-haiku-5-5",
    "gpt-6.1-sol",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "deepseek-v4-pro",
]

AUTO_ORDER_PAID: list[str] = [
    "grok-4.7",
    "qwen3.8-max-0902",
    "gpt-6-astra",
    "claude-sonnet-5-5",
    "claude-opus-5-5",
    "claude-fable-5-1",
]

NO_VISION_MODELS: frozenset[str] = frozenset({"deepseek-v4-pro"})

MODEL_DISPLAY: dict[str, str] = {
    "glm-5.3-flash": "🧊 GLM 5.3 Flash",
    "deepseek-v4.1-flash": "🐋 DeepSeek V4.1 Flash",
    "kimi-k3": "🌙 Kimi K3",
    "deepseek-v4-pro": "🐳 DeepSeek V4 Pro",
    "gpt-6-luna": "🌑 GPT-6 Luna",
    "claude-haiku-5-5": "🎐 Claude Haiku 5.5",
    "gpt-6.1-sol": "☀️ GPT-6.1 Sol",
    "gpt-6-astra": "🪐 GPT-6 Astra",
    "grok-4.7": "🌀 Grok 4.7",
    "claude-fable-5-1": "🎻 Claude Fable 5.1",
    "claude-opus-5-5": "🎭 Claude Opus 5.5",
    "claude-sonnet-5-5": "🎼 Claude Sonnet 5.5",
    "qwen3.8-max-0902": "🐉 Qwen3.8 Max",
    "gemini-3.8-flash": "🚀 Gemini 3.8 Flash",
    "gemini-3.7-flash": "⚡ Gemini 3.7 Flash",
    "gemini-3.6-flash": "🌠 Gemini 3.6 Flash",
    "gemini-3.5-flash": "💫 Gemini 3.5 Flash",
    "gemini-3.5-flash-lite": "✨ Gemini 3.5 Flash Lite",
    "gemini-2.5-flash": "🌟 Gemini 2.5 Flash",
    "gemini-2.5-flash-lite": "💡 Gemini 2.5 Flash Lite",
}

MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-6-astra": {"input": 0.34, "output": 1.7, "cache_read": 0.034, "cache_write": 0.0},
    "grok-4.7": {"input": 0.2, "output": 1.0, "cache_read": 0.02, "cache_write": 0.0},
    "claude-fable-5-1": {"input": 1.2, "output": 6.0, "cache_read": 0.12, "cache_write": 1.2},
    "claude-opus-5-5": {"input": 0.6, "output": 3.2, "cache_read": 0.06, "cache_write": 0.6},
    "claude-sonnet-5-5": {"input": 0.4, "output": 2.0, "cache_read": 0.04, "cache_write": 0.4},
    "qwen3.8-max-0902": {"input": 0.2, "output": 1.0, "cache_read": 0.02, "cache_write": 0.0},
}

PAID_MODELS = tuple(MODEL_PRICING.keys())
USD_TO_RUB = float(os.getenv("USD_TO_RUB") or "90")


def is_paid_model(model: str | None) -> bool:
    return bool(model and model in MODEL_PRICING)


def model_cost_rub(model: str, usage: dict[str, Any] | None) -> float:
    """Стоимость запроса в рублях по usage от API."""
    if not usage or model not in MODEL_PRICING:
        return 0.0
    price = MODEL_PRICING[model]
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    details = usage.get("prompt_tokens_details") or {}
    cached = int(details.get("cached_tokens") or usage.get("cache_read_input_tokens") or 0)
    cache_write = int(usage.get("cache_creation_input_tokens") or 0)
    fresh_input = max(0, prompt_tokens - cached - cache_write)
    usd = (
        fresh_input * price["input"]
        + cached * price["cache_read"]
        + cache_write * price["cache_write"]
        + completion_tokens * price["output"]
    ) / 1_000_000.0
    return round(usd * USD_TO_RUB, 6)


def model_display_name(model: str | None, lang: str = "ru") -> str:
    if not model:
        return "🎲 авто (все подряд)" if lang == "ru" else "🎲 auto (all models)"
    if model.startswith("claude-"):
        parts = model.split("-")
        family = parts[1].capitalize() if len(parts) > 1 else "Claude"
        ver = ".".join(parts[2:]) if len(parts) > 2 else ""
        return f"Claude {family} {ver}".strip()
    return MODEL_DISPLAY.get(model, model)


LOG_INTRO = "🍷🗿 Вот логи сервера, босс:"
PREMIUM_ADMIN_ID = 1420898868


# ============================================================
# PREMIUM FUNCTIONS STATE
# ------------------------------------------------------------
# Раньше сбрасывался в True при каждом рестарте. Теперь хранится
# в data/premium.json и переключается через set_premium_functions_enabled.
# ============================================================
def _load_premium_state() -> bool:
    try:
        if os.path.isfile(PREMIUM_STATE_FILE):
            with open(PREMIUM_STATE_FILE, encoding='utf-8') as f:
                return bool(json.load(f).get('enabled', True))
    except Exception:
        pass
    return True


def _save_premium_state(enabled: bool) -> None:
    try:
        with open(PREMIUM_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'enabled': bool(enabled)}, f)
    except Exception as e:
        logger.warning(f"premium state save: {e}")


premium_functions_enabled: bool = _load_premium_state()


def set_premium_functions_enabled(enabled: bool) -> None:
    global premium_functions_enabled
    premium_functions_enabled = bool(enabled)
    _save_premium_state(premium_functions_enabled)


AUTHORIZED_UPDATERS = [735217033867821098, 1193627300797878362]

COMMUNICATION_MODES = ("kent", "assistant", "pro")
DEFAULT_COMMUNICATION_MODE = "kent"
DS_SCOPES = ("self", "shared")


def mode_is_valid(mode: str) -> bool:
    return mode in COMMUNICATION_MODES


DECO = {
    "sparkle": "✦", "wave": "彡", "rivers": "巛", "stroke": "〢",
    "line": "─", "dline": "═", "dot": "▪", "hollow": "▫",
    "arrow": "▸", "diamond": "◈", "star": "★", "star_hollow": "☆",
    "flower": "❋", "dash": "─", "bul": "•",
}


def deco_divider(length: int = 20, char: str = "─") -> str:
    return char * length


def deco_title(text: str, lang: str = "ru") -> str:
    return f"**{text}**"


RICH_DIVIDER = "---"


def rich_divider() -> str:
    return RICH_DIVIDER


# ============================================================
# VOICE / TTS
# ============================================================
voice_recv: Any = None
sr: Any = None
AudioSegment: Any = None
edge_tts: Any = None
voice_recv_available: bool = False
voice_recognition_enabled: bool = False
voice_enabled: bool = False
try:
    from discord.ext import voice_recv as _voice_recv
    voice_recv = _voice_recv
    voice_recv_available = True
except ImportError:
    voice_recv_available = False

DISCORD_VERSION = tuple(map(int, discord.__version__.split('.')))
voice_recognition_enabled = DISCORD_VERSION >= (2, 0, 0) and voice_recv_available
if voice_recognition_enabled:
    try:
        import speech_recognition as _sr
        from pydub import AudioSegment as _AudioSegment
        sr = _sr
        AudioSegment = _AudioSegment
    except ImportError:
        voice_recognition_enabled = False
        logger.info("⚠️ speech_recognition/pydub не найдены")
else:
    logger.info(f"⚠️ discord.py {discord.__version__}, voice_recv недоступен")

try:
    import edge_tts as _edge_tts
    from discord import FFmpegPCMAudio as _FFmpegPCMAudio
    edge_tts = _edge_tts
    FFmpegPCMAudio = _FFmpegPCMAudio
    voice_enabled = True
except ImportError:
    voice_enabled = False
    logger.info("⚠️ edge_tts/FFmpeg не найдены")


JsonDict: TypeAlias = dict[str, Any]
Color: TypeAlias = str | tuple[int, int, int]
Font: TypeAlias = ImageFont.FreeTypeFont | ImageFont.ImageFont
SearchHit: TypeAlias = dict[str, str]
ChartTheme: TypeAlias = dict[str, Any]
SeriesSpec: TypeAlias = dict[str, Any]

last_search_sources: dict[str, list[SearchHit]] = {}
HandlerT = TypeVar("HandlerT", bound=Callable[..., Any])


class _TypedHandler(Protocol):
    def __call__(self, handler: HandlerT) -> HandlerT: ...


def typed_decorator(decorator: Callable[..., Any]) -> Callable[..., _TypedHandler]:
    return cast(Callable[..., _TypedHandler], decorator)


def cb_id(call: types.CallbackQuery) -> int:
    return cast(int, call.id)


def tg_msg(call: types.CallbackQuery) -> types.Message:
    message = call.message
    if not isinstance(message, types.Message):
        raise RuntimeError("callback has no accessible message")
    return message


def ds_user(bot: discord.Client) -> discord.ClientUser:
    user = bot.user
    if user is None:
        raise RuntimeError("discord bot is not ready")
    return user


def as_member(user: discord.abc.User) -> discord.Member | None:
    return user if isinstance(user, discord.Member) else None


def voice_client(guild: discord.Guild | None) -> discord.VoiceClient | None:
    if guild is None or guild.voice_client is None:
        return None
    client = guild.voice_client
    return client if isinstance(client, discord.VoiceClient) else None


def messageable(channel: discord.abc.Messageable | None) -> discord.abc.Messageable | None:
    if channel is None:
        return None
    send = getattr(channel, "send", None)
    return channel if callable(send) else None


def json_dict(value: Any) -> JsonDict:
    if isinstance(value, dict):
        return cast(JsonDict, value)
    return {}


def json_str(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def theme_str(theme: ChartTheme, key: str, default: str = "#000000") -> str:
    value = theme.get(key, default)
    return value if isinstance(value, str) else default


# ============================================================
# ГЛОБАЛЬНЫЕ СТРУКТУРЫ
# ============================================================
chat_memories: dict[str, deque[dict[str, Any]]] = {}
voice_text_channels: dict[int, Any] = {}
donations_data: dict[str, Any] = {}
user_configs: defaultdict[str, dict[str, Any]] = defaultdict(dict)
# (chat_id, message_id) -> owner user_id. Используем кортеж, а не только message_id,
# потому что message_id уникален только внутри чата.
config_msg_owners: dict[tuple[int, int], int] = {}
config_trigger_msgs: dict[str, int] = {}
prompt_waiting: dict[int, int] = {}
config_children_msgs: dict[tuple[int, int], list[int]] = {}
ui_flow_by_msg: dict[int, dict[str, Any]] = {}
credits_data: dict[str, dict[str, Any]] = {}
tools_sessions: dict[int, dict[str, Any]] = {}
chat_media_history: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=50))
last_random_reply: dict[str, float] = {}
last_old_reply: dict[str, float] = {}
last_bot_reply: dict[str, float] = {}
battle_media_groups: dict[str, asyncio.Task[None]] = {}
battle_photos: dict[str, list[bytes]] = {}
pending_donations: dict[int, int] = {}
user_looksmaxxing_state: defaultdict[int, bool] = defaultdict(lambda: False)
user_femboy_state: defaultdict[int, bool] = defaultdict(lambda: False)
ds_config_scope: dict[int, str] = {}

DAILY_CREDITS = 500
COST_ARCHIVE_EDIT = 500
COST_CONSOLE_CMD = 25
MAX_FILE_SIZE = 500 * 1024
MAX_TOTAL_UNPACKED = 5 * 1024 * 1024
MAX_FILES = 100


# ============================================================
# ФАЙЛЫ СОСТОЯНИЯ
# ============================================================
def load_json_file(path: str) -> JsonDict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json_dict(json.load(f))
    except Exception:
        return {}


def save_json_file(path: str, data: Any) -> None:
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"save_json_file error: {e}")


donations_data = load_json_file(DONATIONS_FILE)
long_term_memory = load_json_file(MEMORY_FILE)
credits_data = load_json_file(CREDITS_FILE)


def save_donations() -> None:
    save_json_file(DONATIONS_FILE, donations_data)


def save_long_term_memory(data: JsonDict) -> None:
    save_json_file(MEMORY_FILE, data)


def save_credits() -> None:
    save_json_file(CREDITS_FILE, credits_data)


def save_user_configs() -> None:
    try:
        data = {k: dict(v) for k, v in user_configs.items()}
        with open(USER_CONFIGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"save_user_configs: {e}")


def load_user_configs() -> None:
    if not os.path.exists(USER_CONFIGS_FILE):
        return
    try:
        with open(USER_CONFIGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return
        config_map = cast(JsonDict, data)
        for k, v in config_map.items():
            if isinstance(v, dict):
                merged = DEFAULT_USER_CONFIG.copy()
                merged.update(cast(JsonDict, v))
                user_configs[k] = merged
    except Exception as e:
        logger.error(f"load_user_configs: {e}")


def save_ds_scopes() -> None:
    try:
        data = {str(k): v for k, v in ds_config_scope.items()}
        with open(DS_SCOPES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"save_ds_scopes: {e}")


def load_ds_scopes() -> None:
    data = load_json_file(DS_SCOPES_FILE)
    for k, v in data.items():
        try:
            key = int(k)
        except (ValueError, TypeError):
            continue
        s = str(v)
        if s in DS_SCOPES:
            ds_config_scope[key] = s


def save_all_state() -> None:
    """Сохранить всё состояние на диск. Вызывается при выходе и перед git-обновлением."""
    try:
        save_user_configs()
    except Exception as e:
        logger.warning(f"save_all_state/user_configs: {e}")
    try:
        save_long_term_memory(long_term_memory)
    except Exception as e:
        logger.warning(f"save_all_state/long_term_memory: {e}")
    try:
        save_credits()
    except Exception as e:
        logger.warning(f"save_all_state/credits: {e}")
    try:
        save_donations()
    except Exception as e:
        logger.warning(f"save_all_state/donations: {e}")
    try:
        save_ds_scopes()
    except Exception as e:
        logger.warning(f"save_all_state/ds_scopes: {e}")
    try:
        _save_trusted_chats()
    except Exception as e:
        logger.warning(f"save_all_state/trusted_chats: {e}")
    try:
        _save_premium_state(premium_functions_enabled)
    except Exception as e:
        logger.warning(f"save_all_state/premium: {e}")


def get_ds_scope(chat_id: int) -> str:
    return ds_config_scope.get(chat_id, "shared")


def set_ds_scope(chat_id: int, scope: str) -> None:
    if scope not in DS_SCOPES:
        return
    ds_config_scope[chat_id] = scope
    save_ds_scopes()


def add_donation(platform: str, user_id: int, amount: int, name: str = "Аноним") -> None:
    key = f"{platform}_{user_id}"
    donations_data[key] = donations_data.get(key, 0) + amount
    if 'names' not in donations_data:
        donations_data['names'] = {}
    donations_data['names'][key] = name
    save_donations()


def get_top_donators(top_n: int = 10) -> list[tuple[str, int]]:
    totals: dict[str, int] = {}
    names: dict[str, str] = donations_data.get('names', {})
    for key, total in donations_data.items():
        if key == 'names':
            continue
        name = names.get(key, key)
        totals[name] = totals.get(name, 0) + total
    return sorted(totals.items(), key=lambda x: x[1], reverse=True)[:top_n]


# ============================================================
# КРЕДИТЫ
# ============================================================
def today_str() -> str:
    return msk_now().strftime('%Y-%m-%d')


def get_user_credits(platform: str, user_id: int) -> int:
    key = f"{platform}_{user_id}"
    today = today_str()
    entry = credits_data.get(key)
    if not entry or entry.get("last_reset") != today:
        entry = {"credits": DAILY_CREDITS, "last_reset": today}
        credits_data[key] = entry
        save_credits()
    return int(entry["credits"])


def spend_credits(platform: str, user_id: int, amount: int) -> bool:
    key = f"{platform}_{user_id}"
    today = today_str()
    entry: JsonDict | None = credits_data.get(key)
    if not entry or entry.get("last_reset") != today:
        entry = {"credits": DAILY_CREDITS, "last_reset": today}
    if entry["credits"] < amount:
        credits_data[key] = entry
        save_credits()
        return False
    entry["credits"] -= amount
    credits_data[key] = entry
    save_credits()
    return True


# ============================================================
# PER-USER CONFIG
# ============================================================
DEFAULT_USER_CONFIG = {
    "series_reminder_enabled": True,
    "stickers_enabled": True,
    "custom_prompt": None,
    "random_reply_enabled": False,
    "random_messages_enabled": True,
    "model": None,
    "language": "ru",
    "theme": "dark",
    "separate_enabled": True,
    "streaming_enabled": False,
    "tools_enabled": False,
    "web_search_enabled": True,
    "drawing_enabled": True,
    "communication_mode": DEFAULT_COMMUNICATION_MODE,
    "reactions_enabled": True,
}


def get_user_config(platform: str, chat_id: int, user_id: int) -> JsonDict:
    key = f"{platform}_{chat_id}_{user_id}"
    cfg = user_configs.get(key)
    if cfg is None:
        cfg = DEFAULT_USER_CONFIG.copy()
        user_configs[key] = cfg
    else:
        for k, v in DEFAULT_USER_CONFIG.items():
            if k not in cfg:
                cfg[k] = v
    if cfg.get("separate_enabled", True) and cfg.get("streaming_enabled", False):
        cfg["streaming_enabled"] = False
    if not mode_is_valid(str(cfg.get("communication_mode", DEFAULT_COMMUNICATION_MODE))):
        cfg["communication_mode"] = DEFAULT_COMMUNICATION_MODE
    return cfg


def bind_ui_flow(bot_message_id: int | None, chat_id: int, user_id: int,
                 origin_id: int | None = None,
                 extra: list[tuple[int, int]] | None = None) -> None:
    """Запоминает, какая команда открыла этот экран, чтобы «Закрыть» удалило и её."""
    if not bot_message_id:
        return
    ui_flow_by_msg[bot_message_id] = {
        "chat_id": chat_id,
        "user_id": user_id,
        "origin_id": origin_id,
        "extra": list(extra or []),
    }


def take_ui_flow(bot_message_id: int) -> dict[str, Any] | None:
    return ui_flow_by_msg.pop(bot_message_id, None)


def get_effective_config(platform: str, chat_id: int, user_id: int) -> JsonDict:
    if platform == "ds" and get_ds_scope(chat_id) == "shared":
        return get_user_config("ds", chat_id, 0)
    return get_user_config(platform, chat_id, user_id)


def get_write_config(platform: str, chat_id: int, user_id: int) -> JsonDict:
    if platform == "ds" and get_ds_scope(chat_id) == "shared":
        return get_user_config("ds", chat_id, 0)
    return get_user_config(platform, chat_id, user_id)


def get_chat_key(platform: str, chat_id: int) -> str:
    return f"{platform}_{chat_id}"


# ============================================================
# LOG TAIL / CHUNK
# ============================================================
def read_log_tail(max_lines: int = 20) -> str:
    try:
        with open(BOT_LOG_FILE, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        if not lines:
            return "Логи пусты."
        return "".join(lines[-max_lines:]).rstrip('\n')
    except FileNotFoundError:
        return "Файл bot.log не найден."
    except Exception as e:
        return f"Ошибка чтения логов: {e}"


def chunk_text(text: str, size: int) -> list[str]:
    if not text:
        return [""]
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) <= size:
            current += line
        else:
            if current:
                chunks.append(current)
            while len(line) > size:
                chunks.append(line[:size])
                line = line[size:]
            current = line
    if current:
        chunks.append(current)
    return chunks


# ============================================================
# ПАМЯТЬ ЧАТА
# ============================================================
def get_chat_memory(chat_id: str) -> deque[dict[str, Any]]:
    if chat_id not in chat_memories:
        chat_memories[chat_id] = deque(maxlen=20)
    return chat_memories[chat_id]


def add_user_memory(
    chat_id: str,
    platform: str,
    display_name: str | None,
    username: str | None,
    user_id: int,
    text: str | None,
    media: list[str] | None = None,
    message_id: int | None = None,
) -> None:
    mem = get_chat_memory(chat_id)
    mem.append({
        "type": "user", "time": msk_time_str(), "ts": time.time(), "platform": platform,
        "display": display_name or "Unknown", "username": username or "",
        "id": str(user_id), "text": text or "",
        "media": media or [], "message_id": message_id,
    })


def add_bot_memory(chat_id: str, text: str, message_id: int | None = None) -> None:
    mem = get_chat_memory(chat_id)
    mem.append({
        "type": "bot", "time": msk_time_str(), "ts": time.time(),
        "text": text or "", "message_id": message_id,
    })


def memory_to_messages(mem_deque: deque[dict[str, Any]]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    now = time.time()
    for entry in mem_deque:
        ts = entry.get("ts")
        try:
            age = humanize_age(now - float(ts)) if ts else ""
        except (TypeError, ValueError):
            age = ""
        stamp = entry.get("time", "")
        if age:
            stamp = f"{stamp} ({age})"
        if entry.get("type") == "bot":
            messages.append({"role": "model", "text": f"[{stamp}] {entry.get('text', '')}"})
        else:
            uname = f"@{entry['username']}" if entry.get("username") else "no-username"
            media_str = ""
            if entry.get("media"):
                media_str = f" [прикрепил: {', '.join(entry['media'])}]"
            mid = entry.get("message_id")
            mid_str = f", msg_id:{mid}" if mid else ""
            prefix = (f"[{stamp}] [{entry.get('platform','')}] "
                      f"{entry.get('display','?')} ({uname}, id:{entry.get('id','?')}{mid_str})")
            messages.append({"role": "user", "text": f"{prefix}{media_str}: {entry.get('text','')}"})
    return messages


def add_media_history(
    chat_id: str,
    url: str | None,
    media_type: str,
    sender: str,
    file_id: str | None = None,
    caption: str = "",
    message_id: int | None = None,
) -> None:
    chat_media_history[chat_id].append({
        "url": url, "type": media_type, "sender": sender,
        "file_id": file_id, "caption": caption,
        "message_id": message_id,
        "time": msk_now().strftime('%d.%m %H:%M'),
    })


def find_media_by_message_id(chat_id: str, message_id: int) -> dict[str, Any] | None:
    hist = chat_media_history.get(chat_id)
    if not hist:
        return None
    for item in reversed(hist):
        if item.get("message_id") == message_id:
            return item
    return None


# ============================================================
# HTML / MARKDOWN (fallback)
# ============================================================
def markdown_like_to_telegram_html(text: str) -> str:
    if not text:
        return ""
    text = html.escape(text, quote=False)
    text = re.sub(r'```([\s\S]*?)```', lambda m: '<pre>' + m.group(1) + '</pre>', text)
    text = re.sub(r'`([^`\n]+?)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text, flags=re.DOTALL)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text, flags=re.DOTALL)
    text = re.sub(r'(?<!\*)\*(?!\*)([^*\n]+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
    text = re.sub(r'(?<!_)_(?!_)([^_\n]+?)(?<!_)_(?!_)', r'<i>\1</i>', text)
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text, flags=re.DOTALL)
    for tag in ("code", "b", "i", "u", "s", "pre"):
        text = text.replace(f'&lt;{tag}&gt;', f'<{tag}>').replace(f'&lt;/{tag}&gt;', f'</{tag}>')
    text = text.replace('&lt;a href=', '<a href=').replace('&lt;/a&gt;', '</a>')
    return text


async def download_image_bytes(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.read()
            raise Exception(f"Failed to download file: {resp.status}")


async def get_tg_file_bytes(bot: AsyncTeleBot, file_id: str) -> bytes:
    file_info = await bot.get_file(file_id)
    file_path = file_info.file_path
    url = f"https://api.telegram.org/file/bot{TG_TOKEN}/{file_path}"
    return await download_image_bytes(url)


def image_bytes_to_base64(image_bytes: bytes, mime_type: str = "image/jpeg") -> tuple[str, str]:
    encoded = base64.b64encode(image_bytes).decode('utf-8')
    return encoded, mime_type


async def extract_video_frame(video_bytes: bytes, ext_hint: str = ".mp4") -> bytes | None:
    path = None
    out_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext_hint, delete=False) as f:
            f.write(video_bytes)
            path = f.name
        out_path = path + ".jpg"
        await asyncio.to_thread(
            subprocess.run,
            ["ffmpeg", "-y", "-i", path, "-vf", "select=eq(n\\,0)",
             "-vframes", "1", "-q:v", "3", out_path],
            capture_output=True, timeout=40,
        )
        if os.path.exists(out_path):
            with open(out_path, 'rb') as f:
                data = f.read()
            return data if data else None
        return None
    except Exception as e:
        logger.warning(f"extract_video_frame: {e}")
        return None
    finally:
        for p in (path, out_path):
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except Exception:
                    pass


# ============================================================
# TYPING
# ============================================================
TYPING_MS_PER_CHAR_MIN = 0.018
TYPING_MS_PER_CHAR_MAX = 0.050
TYPING_MIN_DELAY = 0.35
TYPING_MAX_DELAY = 5.0
TYPING_JITTER_MIN = 0.85
TYPING_JITTER_MAX = 1.25
SEPARATED_TYPING_MULTIPLIER = 2.4


def calc_typing_delay(text: str, segment_index: int = 0) -> float:
    if not text:
        return TYPING_MIN_DELAY
    n = len(text)
    per_char = random.uniform(TYPING_MS_PER_CHAR_MIN, TYPING_MS_PER_CHAR_MAX)
    delay = n * per_char
    delay *= random.uniform(TYPING_JITTER_MIN, TYPING_JITTER_MAX)
    if segment_index > 0:
        delay *= SEPARATED_TYPING_MULTIPLIER
    return max(TYPING_MIN_DELAY, min(TYPING_MAX_DELAY * (1 + segment_index * 0.5), delay))


def clean_json_text(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


# ============================================================
# УТИЛИТЫ-МАРКЕРЫ
# ============================================================
UTILITY_PATTERNS = {
    "avatar": re.compile(r'!\s*avatar(?![A-Za-z])', re.IGNORECASE),
    "recall_media": re.compile(r'!\s*recall[\s_]*media(?![A-Za-z])', re.IGNORECASE),
    "sticker": re.compile(r'!\s*sticker(?![A-Za-z])', re.IGNORECASE),
    "gif": re.compile(r'!\s*gif(?![A-Za-z])', re.IGNORECASE),
    "group_info": re.compile(r'!\s*group[\s_]*info(?![A-Za-z])', re.IGNORECASE),
    "user_info": re.compile(r'!\s*user[\s_]*info(?::\s*(\d+))?(?![A-Za-z])', re.IGNORECASE),
}
STRAY_EXTRA_PATTERNS = (
    re.compile(r'!\s*draw\b', re.IGNORECASE),
    re.compile(r'!\s*term\b[^\n]*', re.IGNORECASE),
)
SEPARATOR_PATTERN = re.compile(
    r'!+\s*sep(?:[ae]rate)?(?![A-Za-z])',
    re.IGNORECASE,
)
# Голый маркер без "!" (модель иногда забывает восклицательный знак).
# Ловим только безопасные случаи, чтобы не съесть обычное английское слово
# "separate" в тексте: маркер либо стоит отдельной строкой, либо приклеен
# к тексту/пунктуации с обеих сторон без пробелов.
BARE_SEPARATOR_PATTERN = re.compile(
    r'(?:^[ \t]*(?:sep|separate)[ \t]*[.!]?[ \t]*$'
    r'|(?<=[^\sA-Za-z0-9])(?:sep|separate)(?=[^\sA-Za-z0-9]))',
    re.IGNORECASE | re.MULTILINE,
)
SEPARATOR_ANY_PATTERN = re.compile(
    SEPARATOR_PATTERN.pattern + '|' + BARE_SEPARATOR_PATTERN.pattern,
    re.IGNORECASE | re.MULTILINE,
)
NO_SPLIT_MARKER = "\u2063\u2063"
REACT_PATTERN = re.compile(
    r'(?:!\s*(?:react|реакция)\s*:?\s*([^\s\n]+)'
    r'|[\[\(]\s*реакция\s*:?\s*([^\s\n\]\)]+(?:\s*[^\s\n\]\)]+)*?)\s*[\]\)])',
    re.IGNORECASE,
)
REACT_STRICT_PATTERN = re.compile(
    r'!\s*(?:react|реакция)\s*:\s*([^\s\n]+)',
    re.IGNORECASE,
)
WHY_PATTERN = re.compile(r'!\s*why\s*:\s*([^\n]+)', re.IGNORECASE)

SEARCH_MARKER_PATTERN = re.compile(r'!\s*search(?![A-Za-z])', re.IGNORECASE)
CHART_MARKER_PATTERN = re.compile(r'!\s*chart(?![A-Za-z])', re.IGNORECASE)

RECALL_MEDIA_ID_PATTERN = re.compile(
    r'!\s*recall[\s_]*media\s*:?\s*(\d+)',
    re.IGNORECASE,
)


def split_by_separator(text: str) -> list[str]:
    """Разбивает по !separate (или просто separate). Без ограничений по количеству."""
    if not text:
        return []
    parts = SEPARATOR_ANY_PATTERN.split(text)
    return [p.strip() for p in parts if p and p.strip()]


def extract_utility_markers(text: str) -> tuple[str, list[str], dict[str, str]]:
    text = text or ""
    markers: list[str] = []
    extras: dict[str, str] = {}
    for name, pat in UTILITY_PATTERNS.items():
        m = pat.search(text)
        if m:
            markers.append(name)
            if name == "user_info" and m.group(1):
                extras["user_info_id"] = m.group(1)
        text = pat.sub(' ', text)
    rm = RECALL_MEDIA_ID_PATTERN.search(text)
    if rm:
        extras["recall_media_id"] = rm.group(1)
        text = RECALL_MEDIA_ID_PATTERN.sub(' ', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'[ \t]+([,.!?;:])(?=[ \t\n]|$)', r'\1', text)
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip(), markers, extras


def dedupe_markers(markers: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in markers:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def _is_structured(text: str) -> bool:
    return bool(re.search(r'```|^\s*[-*+]\s|^\s*\d+\.\s|^#{1,6}\s|^\|', text, re.MULTILINE))


def _split_on_blank_lines(text: str) -> list[str]:
    if _is_structured(text):
        return [text]
    parts = [p.strip() for p in re.split(r'\n\s*\n', text.strip()) if p.strip()]
    if not (2 <= len(parts) <= 4):
        return [text]
    if any(len(p) < 4 for p in parts):
        return [text]
    if sum(1 for p in parts if len(p) > 400) > 1:
        return [text]
    return parts


def _auto_split_sentences(text: str) -> list[str]:
    if not text or len(text) < 90:
        return [text]
    if _is_structured(text):
        return [text]
    parts = re.split(r'(?<=[.!?…])\s+(?=[A-ZА-ЯЁ0-9«"(])', text.strip())
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) < 2 or len(parts) > 5:
        lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
        if 2 <= len(lines) <= 5:
            parts = lines
        else:
            return [text]
    if any(len(p) < 8 for p in parts):
        return [text]
    return parts


def process_ai_response(raw: str, separate_enabled: bool = True) -> tuple[list[str], list[str]]:
    raw_clean, markers, _ = extract_utility_markers(raw or "")
    markers = dedupe_markers(markers)
    if raw_clean.startswith(NO_SPLIT_MARKER):
        single = raw_clean[len(NO_SPLIT_MARKER):].strip()
        return ([single] if single else []), markers
    raw_clean = strip_time_prefixes(raw_clean, as_separator=separate_enabled)
    if separate_enabled:
        segments = split_by_separator(raw_clean)
        if len(segments) <= 1 and raw_clean.strip():
            segments = _split_on_blank_lines(raw_clean.strip())
        if len(segments) <= 1 and raw_clean.strip():
            segments = _auto_split_sentences(raw_clean.strip())
    else:
        raw_clean = SEPARATOR_ANY_PATTERN.sub(' ', raw_clean)
        raw_clean = re.sub(r'[ \t]{2,}', ' ', raw_clean).strip()
        raw_clean = re.sub(r'\n{2,}', '\n', raw_clean)
        segments = [raw_clean]
    clean_segments = [s.strip() for s in segments if s and s.strip()]
    return clean_segments, markers


# ============================================================
# ТИПОГРАФИКА
# ------------------------------------------------------------
# Модель регулярно игнорирует просьбы в промпте писать дефис вместо
# длинного тире и обычные кавычки вместо «ёлочек». Поэтому дополнительно
# нормализуем текст пост-фактум. Блоки кода (```...```) и inline-code
# (`...`) не трогаем — там символы могут быть осмысленными.
# ============================================================
_FENCE_SPLIT_RE = re.compile(r'(```[\s\S]*?```)')
_INLINE_CODE_SPLIT_RE = re.compile(r'(`[^`\n]+`)')


def normalize_typography(text: str) -> str:
    """Заменяет типографские символы на клавиатурные в обычном тексте.
    Блоки кода ``` ... ``` и inline-code `...` не изменяются."""
    if not text:
        return text
    parts = _FENCE_SPLIT_RE.split(text)
    out: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            out.append(part)
            continue
        sub_parts = _INLINE_CODE_SPLIT_RE.split(part)
        sub_out: list[str] = []
        for j, sub in enumerate(sub_parts):
            if j % 2 == 1:
                sub_out.append(sub)
                continue
            sub = re.sub(r'[—–]', '-', sub)
            sub = sub.replace('«', '"').replace('»', '"')
            sub = sub.replace('„', '"').replace('‟', '"')
            sub = re.sub(r'[“”]', '"', sub)
            sub = re.sub(r'[‘’‚‛]', "'", sub)
            sub_out.append(sub)
        out.append(''.join(sub_out))
    return ''.join(out)


# ============================================================
# ПУНКТУАЦИЯ ДЛЯ ЧАТА
# ------------------------------------------------------------
# Проблема: модели с сильным грамматическим датасетом ставят запятые
# перед "и/но/что/как/когда/если/хотя/пока" — по правилам русского
# языка. Но в чате так не пишут.
#
# Не трогает:
#   - блоки кода и inline-code
#   - списки, таблицы, заголовки
#   - длинные сообщения
#   - вопросительный знак и …
# ============================================================
_CHAT_COMMAS_TO_DROP = re.compile(
    r',\s+(?=(?:и|но|что|чтобы|чтоб|как|когда|если|хотя|пока)\b)',
    re.IGNORECASE,
)
_CHAT_TRAILING_DOT = re.compile(r'[.!]+\s*$')
_CHAT_LONG_LIMIT = 180
_CHAT_SHORT_LIMIT = 140


def _is_structured_chat_text(text: str) -> bool:
    if not text:
        return False
    if '```' in text or '`' in text:
        return True
    if re.search(r'^\s*[-*+]\s|^\s*\d+\.\s|^#{1,6}\s|^\|', text, re.MULTILINE):
        return True
    if '!draw' in text or '!chart' in text or '!search' in text:
        return True
    return False


def strip_chat_punctuation(text: str) -> str:
    """Убирает лишнюю пунктуацию, которую модель ставит по правилам грамматики.
    В чате так не пишут. Применять ТОЛЬКО в режиме кента.
    """
    if not text:
        return text
    if _is_structured_chat_text(text):
        return text
    if len(text) > _CHAT_LONG_LIMIT:
        return text
    text = _CHAT_COMMAS_TO_DROP.sub(' ', text)
    if len(text) <= _CHAT_SHORT_LIMIT:
        text = _CHAT_TRAILING_DOT.sub('', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()


def scrub_stray_markers(text: str) -> str:
    """Страховка: удаляет уцелевшие служебные маркеры и голые '!' перед буквами."""
    if not text:
        return text
    text = normalize_typography(text)
    pats = [
        SEPARATOR_ANY_PATTERN,
        REACT_STRICT_PATTERN,
        REACT_PATTERN,
        WHY_PATTERN,
        SEARCH_MARKER_PATTERN,
        CHART_MARKER_PATTERN,
        RECALL_MEDIA_ID_PATTERN,
        *UTILITY_PATTERNS.values(),
        *STRAY_EXTRA_PATTERNS,
    ]
    for pat in pats:
        text = pat.sub(' ', text)
    text = re.sub(r'!\s*(?=[а-яёА-ЯЁ])', '', text)
    text = re.sub(r'!\s*(?:react|реакция|why|separate|sep[ae]rate)\b\s*:?', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'[ \t]+([,.!?;:])(?=[ \t\n]|$)', r'\1', text)
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = strip_time_prefixes(text, as_separator=False)
    text = text.replace("\u2063", "")
    return text.strip()


_TIME_PREFIX_RE = re.compile(
    r'^\s*'
    r'(?:'
    r'\[\s*\d{1,2}[:.]\d{2}(?::\d{2})?(?:\s*(?:МСК|MSK))?\s*(?:\([^)\]]*\))?\s*\]'
    r'|\(\s*(?:(?:сегодня|today)\s+)?\d{1,2}[:.]\d{2}(?::\d{2})?(?:\s*(?:МСК|MSK))?\s*(?:\([^)]*\))?\s*\)'
    r'|\d{1,2}[:.]\d{2}(?::\d{2})?(?:\s*(?:МСК|MSK))?\s*[:：\-—]'
    r'|\d{1,2}[:.]\d{2}(?::\d{2})?(?:\s*(?:МСК|MSK))?\s*\([^)\n]*\)'
    r')'
    r'\s*'
    r'(?:(?:сегодня|today)\s*[,:\-—]?\s*)?'
)


def strip_time_prefixes(text: str, as_separator: bool = True) -> str:
    if not text:
        return text
    out: list[str] = []
    in_code = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
            out.append(line)
            continue
        if in_code:
            out.append(line)
            continue
        m = _TIME_PREFIX_RE.match(line)
        if not m:
            out.append(line)
            continue
        rest = line[m.end():].lstrip(" \t-—:.,")
        if not rest:
            continue
        if as_separator and any(part.strip() for part in out):
            out.append("!separate")
        out.append(rest)
    return "\n".join(out)


EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002600-\U000027BF"
    "\U0001F000-\U0001F2FF"
    "\U00002B00-\U00002BFF"
    "\U0000FE00-\U0000FE0F"
    "\U00002190-\U000021FF"
    "\U0001F900-\U0001F9FF"
    "\U00002700-\U000027BF"
    "]+",
    flags=re.UNICODE,
)
_KENT_ALLOWED_EMOJI = ("🍷", "🗿")


def strip_chat_emojis(text: str) -> str:
    if not text:
        return text

    def _keep(match: "re.Match[str]") -> str:
        seq = match.group(0)
        keep = "".join(ch for ch in seq if ch in _KENT_ALLOWED_EMOJI)
        return keep

    text = EMOJI_RE.sub(_keep, text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'[ \t]+([,.!?;:])(?=[ \t\n]|$)', r'\1', text)
    text = re.sub(r'[ \t]+\n', '\n', text)
    return text.strip()


def extract_reaction_and_why(text: str) -> tuple[str, str | None, str | None]:
    if not text:
        return "", None, None
    react_match = REACT_STRICT_PATTERN.search(text) or REACT_PATTERN.search(text)
    why_match = WHY_PATTERN.search(text)
    emojis: str | None = None
    why: str | None = None
    if react_match:
        emojis = (react_match.group(1) or (react_match.group(2) if react_match.lastindex and react_match.lastindex >= 2 else None) or "").strip() or None
    if why_match:
        why = why_match.group(1).strip()
    cleaned = REACT_STRICT_PATTERN.sub(' ', text)
    cleaned = REACT_PATTERN.sub(' ', cleaned)
    cleaned = WHY_PATTERN.sub(' ', cleaned)
    cleaned = re.sub(r'[ \t]{2,}', ' ', cleaned).strip()
    return cleaned, emojis, why


def split_emojis(emojis: str) -> list[str]:
    if not emojis:
        return []
    out: list[str] = []
    i = 0
    while i < len(emojis):
        cp = ord(emojis[i])
        if 0xFE00 <= cp <= 0xFE0F or cp in (0x200D,):
            i += 1
            continue
        if 0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or 0x2B00 <= cp <= 0x2BFF \
                or 0x1F1E6 <= cp <= 0x1F1FF:
            j = i + 1
            while j < len(emojis) and (
                ord(emojis[j]) == 0x200D
                or 0xFE00 <= ord(emojis[j]) <= 0xFE0F
                or 0x1F000 <= ord(emojis[j]) <= 0x1FAFF
            ):
                j += 1
            out.append(emojis[i:j])
            i = j
        else:
            i += 1
    return out


def clean_extra_text(raw: str) -> list[str]:
    if not raw:
        return []
    raw = normalize_typography(raw)
    cleaned, _, _ = extract_utility_markers(raw)
    cleaned = SEPARATOR_ANY_PATTERN.sub(' ', cleaned)
    cleaned = REACT_STRICT_PATTERN.sub(' ', cleaned)
    cleaned = REACT_PATTERN.sub(' ', cleaned)
    cleaned = WHY_PATTERN.sub(' ', cleaned)
    cleaned = re.sub(r'[ \t]{2,}', ' ', cleaned).strip()
    return [s.strip() for s in cleaned.split('\n\n') if s and s.strip()]


STICKER_POOL = [
    "CAACAgEAAxkBAAEXkj1qd6YOMXAHLciofztbliRFn-qf5gACvAIAAmIaIUTfm-IZfGZGmj0E",
    "CAACAgEAAxkBAAEXkj9qd6YSbqnaV0Cy2lJdQZxWgfdYNAACCQIAAvGaoUbqHGwx5EW7xT0E",
    "CAACAgIAAxkBAAEXkkFqd6Yk_g5UWkBESTIlZCT9MM7lZwACBVMAAlXDoUv4ZxNfrA5v8D0E",
    "CAACAgIAAxkBAAEXkkNqd6YlWmX_v6vxFgVS-5u8SMFqGwACJ0wAAlzgmUtxWCk2-pvTsT0E",
    "CAACAgIAAxkBAAEXkkVqd6YmKSS74hvpUNctJPyOg80O2wAC1EgAAsKvmUsRFrgOElSDWz0E",
]
GIF_POOL = [
    "https://cdn.discordapp.com/attachments/1494583947664035913/1535766838695301150/moai_20260808214829.gif",
    "https://cdn.discordapp.com/attachments/1494583947664035913/1535766152716882030/wine_20260808214547.gif",
    "https://cdn.discordapp.com/attachments/1494583947664035913/1535766838384791592/moai2_20260808214836.gif",
    "https://cdn.discordapp.com/attachments/1494583947664035913/1535766838070345829/freedom_20260808214842.gif",
    "https://cdn.discordapp.com/attachments/1494583947664035913/1535766837772427294/octopus_20260808214849.gif",
]


# ============================================================
# LOOKSMAXXING TIERS
# ============================================================
TIER_DISTRIBUTION: list[dict[str, str | float]] = [
    {"key": "sub3",     "short": "S3",  "full_m": "SUB 3",     "full_f": "SUB 3",     "psl_low": 1.0, "psl_high": 2.4},
    {"key": "sub5",     "short": "S5",  "full_m": "SUB 5",     "full_f": "SUB 5",     "psl_low": 2.5, "psl_high": 3.9},
    {"key": "ltn",      "short": "LTN", "full_m": "LTN",       "full_f": "LTB",       "psl_low": 4.0, "psl_high": 5.5},
    {"key": "mtn",      "short": "MTN", "full_m": "MTN",       "full_f": "MTB",       "psl_low": 5.6, "psl_high": 6.3},
    {"key": "htn",      "short": "HTN", "full_m": "HTN",       "full_f": "HTB",       "psl_low": 6.4, "psl_high": 6.9},
    {"key": "chadlite", "short": "CL",  "full_m": "CHADLITE",  "full_f": "STACYLITE", "psl_low": 7.0, "psl_high": 7.4},
    {"key": "chad",     "short": "CH",  "full_m": "CHAD",      "full_f": "STACY",     "psl_low": 7.5, "psl_high": 7.6},
    {"key": "adamlite", "short": "AL",  "full_m": "ADAMLITE",  "full_f": "EVELITE",   "psl_low": 7.7, "psl_high": 7.8},
    {"key": "trueadam", "short": "TA",  "full_m": "TRUE ADAM", "full_f": "TRUE EVE",  "psl_low": 7.9, "psl_high": 8.0},
]


def find_tier_key(tier_name: str) -> str | None:
    if not tier_name:
        return None
    tn = tier_name.strip().upper().replace("_", " ").replace("-", " ")
    for tr_ in TIER_DISTRIBUTION:
        candidates = [str(tr_["key"]).upper(), str(tr_["short"]).upper(),
                      str(tr_["full_m"]).upper(), str(tr_["full_f"]).upper()]
        if tn in candidates or tn.replace(" ", "") in [c.replace(" ", "") for c in candidates]:
            return str(tr_["key"])
    return None


def get_tier_color(tier_key_or_name: str) -> str:
    key = find_tier_key(tier_key_or_name) or (tier_key_or_name or "").strip().lower()
    if key in ("sub3", "sub5"):
        return "#E53E3E"
    if key in ("ltn", "mtn"):
        return "#ECC94B"
    if key in ("htn", "chadlite", "chad", "adamlite"):
        return "#38A169"
    if key == "trueadam":
        return "#9F7AEA"
    return "#38A169"


def is_looksmaxxing_command(text: str) -> bool:
    t = (text or "").strip().lower()
    return bool(re.match(r'^(кульш\s+)?psl(\s+(совет|advice))?$', t))


def is_battle_command(text: str) -> bool:
    t = (text or "").strip().lower()
    return bool(re.match(r'^(кульш\s+)?(battle|баттл|батл)$', t))


FEMBOY_TIER_DISTRIBUTION: list[dict[str, Any]] = [
    {"key": "chad",     "short": "CHD", "full_m": "CHAD",     "full_f": "CHAD",     "fmb_low": 1.0,  "fmb_high": 2.4,  "color": "#E53E3E"},
    {"key": "sigma",    "short": "SGM", "full_m": "SIGMA",    "full_f": "SIGMA",    "fmb_low": 2.5,  "fmb_high": 3.9,  "color": "#ED8936"},
    {"key": "normie",   "short": "NRM", "full_m": "NORMIE",   "full_f": "NORMIE",   "fmb_low": 4.0,  "fmb_high": 5.4,  "color": "#ECC94B"},
    {"key": "softboy",  "short": "SFB", "full_m": "SOFTBOY",  "full_f": "SOFTGIRL", "fmb_low": 5.5,  "fmb_high": 6.4,  "color": "#48BB78"},
    {"key": "cutie",    "short": "CUT", "full_m": "CUTIE",    "full_f": "CUTIE",    "fmb_low": 6.5,  "fmb_high": 7.4,  "color": "#38B2AC"},
    {"key": "femboy",   "short": "FMB", "full_m": "FEMBOY",   "full_f": "FEMGIRL",  "fmb_low": 7.5,  "fmb_high": 8.4,  "color": "#4299E1"},
    {"key": "twink",    "short": "TWK", "full_m": "TWINK",    "full_f": "TWINK",    "fmb_low": 8.5,  "fmb_high": 9.2,  "color": "#9F7AEA"},
    {"key": "ultrafem", "short": "UFM", "full_m": "ULTRAFEM", "full_f": "ULTRAFEM", "fmb_low": 9.3,  "fmb_high": 9.7,  "color": "#ED64A6"},
    {"key": "goddess",  "short": "GDS", "full_m": "GODDESS",  "full_f": "GODDESS",  "fmb_low": 9.8,  "fmb_high": 10.0, "color": "#F687B3"},
]


def find_femboy_tier_key(name: str) -> str | None:
    if not name:
        return None
    tn = name.strip().upper().replace("_", " ").replace("-", " ")
    for tr_ in FEMBOY_TIER_DISTRIBUTION:
        candidates = [str(tr_["key"]).upper(), str(tr_["short"]).upper(),
                      str(tr_["full_m"]).upper(), str(tr_["full_f"]).upper()]
        if tn in candidates or tn.replace(" ", "") in [c.replace(" ", "") for c in candidates]:
            return str(tr_["key"])
    return None


def get_femboy_tier_color(key_or_name: str) -> str:
    key = find_femboy_tier_key(key_or_name) or (key_or_name or "").strip().lower()
    for tr_ in FEMBOY_TIER_DISTRIBUTION:
        if tr_["key"] == key:
            return str(tr_.get("color") or "#9F7AEA")
    return "#9F7AEA"


def is_femboy_rate_command(text: str) -> bool:
    t = (text or "").strip().lower()
    return bool(re.match(
        r'^(кульш\s+|kulsh\s+)?(femboy\s*rate|фембой\s*рейт|фембой\s*рейтинг|femboy-rate)$',
        t,
    ))


def is_femboy_battle_command(text: str) -> bool:
    t = (text or "").strip().lower()
    return bool(re.match(
        r'^(кульш\s+|kulsh\s+)?(femboy\s*battle|фембой\s*баттл|фембой\s*батл|femboy-battle)$',
        t,
    ))


TIER_RULES_M = "SUB 3, SUB 5, LTN, MTN, HTN, CHADLITE, CHAD, ADAMLITE, TRUE ADAM"
TIER_RULES_F = "SUB 3, SUB 5, LTB, MTB, HTB, STACYLITE, STACY, EVELITE, TRUE EVE"
TIER_RULES_STRICT = (
    f"Мужские тиры (СТРОГО): {TIER_RULES_M}.\n"
    f"Женские тиры (СТРОГО): {TIER_RULES_F}.\n"
    "ИСПОЛЬЗУЙ ТОЛЬКО ЭТИ НАЗВАНИЯ. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать 'High Normie', 'Low Tier Normie', "
    "'Subhuman', 'Sub-five', 'Sub-5 (Canine)', 'Animal' и любые другие выдуманные варианты. "
    "Если на фото не человек — верни tier 'N/A' и gender 'N/A'."
)

FEMBOY_TIER_RULES_M = "CHAD, SIGMA, NORMIE, SOFTBOY, CUTIE, FEMBOY, TWINK, ULTRAFEM, GODDESS"
FEMBOY_TIER_RULES_F = "CHAD, SIGMA, NORMIE, SOFTGIRL, CUTIE, FEMGIRL, TWINK, ULTRAFEM, GODDESS"
FEMBOY_TIER_RULES_STRICT = (
    f"Мужские тиры FMB (СТРОГО): {FEMBOY_TIER_RULES_M}.\n"
    f"Женские тиры FMB (СТРОГО): {FEMBOY_TIER_RULES_F}.\n"
    "ИСПОЛЬЗУЙ ТОЛЬКО ЭТИ НАЗВАНИЯ. Не выдумывай новые. "
    "Если на фото не человек — tier 'N/A', gender 'N/A'."
)


# ============================================================
# SAFE GIT UPDATE
# ============================================================
TEXT_EXTS = {
    "txt", "py", "json", "html", "htm", "js", "css", "cs", "cpp", "c", "h", "hpp",
    "java", "php", "rb", "go", "rs", "ts", "tsx", "jsx", "xml", "yml", "yaml",
    "toml", "ini", "cfg", "conf", "sh", "bash", "bat", "ps1", "sql", "md",
    "log", "env", "gitignore", "dockerfile", "makefile", "vue", "svelte",
    "scss", "sass", "less", "kt", "swift", "dart", "lua", "pl", "r", "m", "mm",
}

SAFE_COMMANDS = {"ls", "cat", "head", "tail", "wc", "grep", "find", "file", "stat", "du", "tree", "pwd"}


def run_git(args: list[str], cwd: str, timeout: int = 60) -> tuple[int, str, str]:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except FileNotFoundError:
        return 127, "", "git not found"
    except Exception as e:
        return 1, "", str(e)


def check_python_syntax(fpath: str) -> str | None:
    try:
        with open(fpath, 'r', encoding='utf-8') as fp:
            src = fp.read()
    except Exception as e:
        return f"read error: {type(e).__name__}: {e}"
    try:
        compile(src, fpath, 'exec')
    except SyntaxError as se:
        return f"SyntaxError: {se.msg} (line {se.lineno})"
    except Exception as e:
        return f"{type(e).__name__}: {e}"
    return None


def check_all_syntax(repo_path: str) -> list[str]:
    errors: list[str] = []
    try:
        for root, _dirs, files in os.walk(repo_path):
            if '.git' in root.split(os.sep) or f'{os.sep}data{os.sep}' in root + os.sep:
                continue
            for fname in files:
                if not fname.endswith('.py'):
                    continue
                fpath = os.path.join(root, fname)
                err = check_python_syntax(fpath)
                if err:
                    rel = os.path.relpath(fpath, repo_path)
                    errors.append(f"{rel}: {err}")
    except Exception as e:
        errors.append(f"walk error: {type(e).__name__}: {e}")
    return errors


def repo_root(fpath: str) -> str:
    directory = os.path.dirname(os.path.abspath(fpath)) or os.getcwd()
    if os.path.basename(directory) == "src":
        return os.path.dirname(directory) or directory
    return directory


def safe_check_import(fpath: str, timeout: int = 60) -> str | None:
    if not os.path.isfile(fpath):
        return None
    root = repo_root(fpath)
    try:
        rel = os.path.relpath(os.path.abspath(fpath), os.path.abspath(root)).replace(os.sep, "/")
    except Exception:
        rel = "src/app.py"
    if rel.endswith(".py"):
        rel = rel[:-3]
    module_name = rel.replace("/", ".")

    script = (
        "import sys\n"
        f"sys.path.insert(0, {root!r})\n"
        "try:\n"
        f"    mod = __import__({module_name!r}, fromlist=['*'])\n"
        "    smoke = getattr(mod, '_smoke_check', None)\n"
        "    if smoke is not None:\n"
        "        smoke()\n"
        "    print('SMOKE_OK')\n"
        "except SystemExit:\n"
        "    print('SMOKE_OK_SYSEXIT')\n"
        "except BaseException:\n"
        "    import traceback\n"
        "    sys.stderr.write(traceback.format_exc())\n"
        "    sys.exit(2)\n"
    )
    try:
        r = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=timeout,
            cwd=root,
        )
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "unknown").strip()
            return err[:1500]
    except subprocess.TimeoutExpired:
        return "timeout при smoke-проверке"
    except Exception as e:
        return f"{type(e).__name__}: {e}"
    return None


def find_entry_file(repo_path: str) -> str | None:
    for cand in ("src/app.py", "kulsh.py", "main.py", "app.py", "bot.py"):
        p = os.path.join(repo_path, cand)
        if os.path.isfile(p):
            return p
    try:
        for f in os.listdir(repo_path):
            if f.endswith(".py") and not f.startswith("_"):
                return os.path.join(repo_path, f)
    except Exception:
        pass
    return None


# Файлы состояния, которые нельзя затирать при git reset --hard.
_STATE_FILE_PATHS: tuple[str, ...] = (
    USER_CONFIGS_FILE, MEMORY_FILE, CREDITS_FILE, DONATIONS_FILE,
    DS_SCOPES_FILE, TRUSTED_CHATS_FILE, PREMIUM_STATE_FILE,
    BALANCES_FILE, DA_PROCESSED_FILE, TICKETS_FILE, DA_TOKEN_FILE,
    PROMO_FILE, ADMIN_USERS_FILE, BLOCK_FILE, ADMIN_REQUESTS_FILE,
    CLOUD_MIGRATED_FILE,
)


def _backup_state_to_tmp() -> dict[str, str]:
    """Копирует все JSON-состояния во временную директорию. Возвращает {orig: backup}."""
    bdir = tempfile.mkdtemp(prefix="kulsh_state_")
    out: dict[str, str] = {}
    for path in _STATE_FILE_PATHS:
        if os.path.isfile(path):
            try:
                dst = os.path.join(bdir, os.path.basename(path))
                shutil.copy2(path, dst)
                out[path] = dst
            except Exception as e:
                logger.warning(f"backup {path}: {e}")
    return out


def _restore_state_from_backup(mapping: dict[str, str]) -> None:
    """Восстанавливает файлы состояния, если их нет или они отличаются от бэкапа."""
    for orig, bak in mapping.items():
        if not os.path.isfile(bak):
            continue
        try:
            if not os.path.isfile(orig):
                shutil.copy2(bak, orig)
                logger.info(f"restored (missing): {orig}")
                continue
            with open(bak, 'rb') as f1, open(orig, 'rb') as f2:
                if f1.read() != f2.read():
                    shutil.copy2(bak, orig)
                    logger.info(f"restored (changed): {orig}")
        except Exception as e:
            logger.warning(f"restore {orig}: {e}")


def _cleanup_backup(mapping: dict[str, str]) -> None:
    if not mapping:
        return
    dirs: set[str] = set()
    for bak in mapping.values():
        dirs.add(os.path.dirname(bak))
        try:
            os.unlink(bak)
        except Exception:
            pass
    for d in dirs:
        try:
            shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass


async def perform_safe_git_update(repo_path: str) -> tuple[str, str]:
    # 1. Сохраняем всё состояние и делаем бэкап ДО любых git-операций.
    try:
        save_all_state()
    except Exception as e:
        logger.warning(f"save before update: {e}")
    backup = _backup_state_to_tmp()
    try:
        return await _perform_safe_git_update_inner(repo_path, backup)
    finally:
        _cleanup_backup(backup)


async def _perform_safe_git_update_inner(
    repo_path: str, backup: dict[str, str],
) -> tuple[str, str]:
    rc, out, err = run_git(["rev-parse", "HEAD"], cwd=repo_path, timeout=10)
    if rc != 0 or not out.strip():
        return "error", f"git rev-parse: {err or out or 'unknown error'}"
    prev_hash = out.strip()

    rc, out, err = run_git(["fetch", "origin", "main"], cwd=repo_path, timeout=60)
    if rc != 0:
        return "error", f"git fetch: {err or out or 'unknown error'}"

    rc, out, err = run_git(["pull", "origin", "main", "--ff-only"], cwd=repo_path, timeout=60)
    pull_out = (out or "") + (err or "")
    if rc != 0:
        rc2, out2, err2 = run_git(["pull", "origin", "main"], cwd=repo_path, timeout=60)
        pull_out += "\n" + (out2 or "") + (err2 or "")
        if rc2 != 0:
            return "error", f"git pull fail:\n{pull_out[:1500]}"

    # После pull восстанавливаем файлы состояния на случай, если они были в репе.
    _restore_state_from_backup(backup)

    if "Already up to date" in pull_out or "Already up-to-date" in pull_out:
        return "up_to_date", pull_out

    MAX_BACK_STEPS = 8
    tried_errors: list[str] = []

    for step in range(0, MAX_BACK_STEPS + 1):
        if step == 0:
            rc_h, out_h, _err_h = run_git(["rev-parse", "HEAD"], cwd=repo_path, timeout=10)
        else:
            rc_h, out_h, _err_h = run_git(["rev-parse", f"HEAD~{step}"], cwd=repo_path, timeout=10)
        if rc_h != 0 or not out_h.strip():
            break
        current_hash = out_h.strip()

        if step > 0:
            rc_reset, out_r, err_r = run_git(["reset", "--hard", current_hash], cwd=repo_path, timeout=30)
            if rc_reset != 0:
                tried_errors.append(f"шаг {step}: git reset --hard fail: {err_r or out_r or 'unknown'}")
                continue
            # После reset --hard восстанавливаем файлы состояния из бэкапа.
            _restore_state_from_backup(backup)

        syntax_errors = check_all_syntax(repo_path)
        if syntax_errors:
            tried_errors.append(
                f"шаг {step} ({current_hash[:7]}): syntax errors:\n" + "\n".join(syntax_errors[:5])
            )
            continue

        entry = find_entry_file(repo_path)
        if entry:
            import_err = await asyncio.to_thread(safe_check_import, entry)
            if import_err:
                tried_errors.append(
                    f"шаг {step} ({current_hash[:7]}): smoke fail:\n{import_err[:800]}"
                )
                continue

        if step == 0:
            logger.info(f"✅ Обновление прошло проверку на {current_hash[:7]}")
            return "ok", pull_out
        else:
            logger.warning(f"⚠️ Откат на {step} коммит(ов) назад → {current_hash[:7]}")
            summary = tried_errors[0] if tried_errors else ""
            return "rolled_back", (
                f"последние {step} коммит(ов) не прошли smoke-проверку. "
                f"Откатился на {current_hash[:7]}.\n\n"
                f"Причина последнего отказа:\n{summary[:1200]}"
            )

    if prev_hash:
        run_git(["reset", "--hard", prev_hash], cwd=repo_path, timeout=30)
        _restore_state_from_backup(backup)
    return "error", (
        f"ни один из последних коммитов (включая откат на {MAX_BACK_STEPS}) не прошёл smoke-проверку. "
        f"Вернул рабочее дерево на {prev_hash[:7]}.\n\n"
        + "\n\n".join(tried_errors[:5])[:1500]
    )


try:
    load_user_configs()
    load_ds_scopes()
    logger.info(f"✅ Загружено настроек пользователей: {len(user_configs)}, DS-scope: {len(ds_config_scope)}")
    logger.info(f"📁 DATA_DIR: {DATA_DIR}")
except Exception as e:
    logger.warning(f"load на старте: {e}")

from src.i18n import TEXTS as TEXTS, html_to_md as html_to_md, tr as tr