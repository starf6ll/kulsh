# Kulsh GPT | генерация и редактирование изображений через Etage One.
# Модель и провайдер нигде не показываются пользователю.

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import random
import re
from collections import deque
from typing import Any, Awaitable, Callable

import aiohttp

from src.util import (
    DATA_DIR,
    ETAGEONE_API_KEY,
    IMAGE_USAGE_FILE,
    logger,
    msk_now,
)

IMAGE_DAILY_LIMIT = 3
IMAGE_API_BASE = "https://api.etage.one/v1"
IMAGE_MODEL = "gpt-image-2.5-flare"

# Внутренние фразы для сообщения прогресса. Ровно 10, строчными буквами,
# простая разговорная речь без переигрывания.
PROGRESS_PHRASES = (
    "рисую...",
    "ща нарисую...",
    "малюю...",
    "колдую над картинкой...",
    "собираю изображение...",
    "пиксели гоняю...",
    "делаю картинку...",
    "творю...",
    "химичу с картинкой...",
    "рисую по-нормальному...",
)

_image_usage: dict[str, dict[str, Any]] = {}
_generated_images: dict[str, deque[dict[str, Any]]] = {}


def _load_usage() -> None:
    global _image_usage
    if not os.path.exists(IMAGE_USAGE_FILE):
        return
    try:
        with open(IMAGE_USAGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _image_usage = {str(k): v for k, v in data.items() if isinstance(v, dict)}
    except Exception as e:
        logger.warning(f"image_usage load: {e}")


def _save_usage() -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(IMAGE_USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(_image_usage, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"image_usage save: {e}")


def _today() -> str:
    return msk_now().strftime("%Y-%m-%d")


def _usage_key(platform: str, user_id: int) -> str:
    return f"{platform}_{user_id}"


def image_used(platform: str, user_id: int) -> int:
    if not user_id:
        return 0
    entry = _image_usage.get(_usage_key(platform, user_id))
    if not entry or entry.get("date") != _today():
        return 0
    try:
        return max(0, int(entry.get("used", 0)))
    except (TypeError, ValueError):
        return 0


def image_remaining(platform: str, user_id: int) -> int:
    return max(0, IMAGE_DAILY_LIMIT - image_used(platform, user_id))


def consume_image(platform: str, user_id: int) -> bool:
    """Списать одну генерацию. Вызывать только после успешной генерации."""
    if not user_id:
        return True
    key = _usage_key(platform, user_id)
    used = image_used(platform, user_id)
    if used >= IMAGE_DAILY_LIMIT:
        return False
    _image_usage[key] = {"date": _today(), "used": used + 1}
    _save_usage()
    return True


def random_progress_phrase() -> str:
    return random.choice(PROGRESS_PHRASES)


def remember_generated_image(chat_key: str, data: bytes, mime: str = "image/png",
                             message_id: int | None = None) -> None:
    if not data:
        return
    bucket = _generated_images.get(chat_key)
    if bucket is None:
        bucket = deque(maxlen=12)
        _generated_images[chat_key] = bucket
    bucket.append({"data": data, "mime": mime, "message_id": message_id})


def recent_generated_images(chat_key: str, limit: int = 4) -> list[bytes]:
    bucket = _generated_images.get(chat_key)
    if not bucket:
        return []
    return [item["data"] for item in list(bucket)[-limit:]][::-1]


def dedupe_refs(refs: list[bytes], limit: int = 4) -> list[bytes]:
    out: list[bytes] = []
    seen: set[int] = set()
    for raw in refs:
        if not raw:
            continue
        # Быстрый отпечаток без лишнего хеширования больших файлов.
        marker = hash(raw[:1024]) ^ len(raw)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(raw)
    return out[:limit]


_IMAGE_RE = re.compile(r"!image\b", re.IGNORECASE)


def extract_image_parts(text: str) -> tuple[dict[str, Any] | None, str, str]:
    """Возвращает (spec, before_text, after_text) для блока !image."""
    if not text:
        return None, "", ""
    m = _IMAGE_RE.search(text)
    if not m:
        return None, "", ""
    before = text[:m.start()].strip()
    rest = text[m.end():].lstrip()
    block = re.match(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", rest, re.IGNORECASE)
    spec_text = ""
    consumed = 0
    if block:
        spec_text = block.group(1)
        consumed = block.end()
    else:
        start = rest.find("{")
        end = rest.rfind("}")
        if start != -1 and end > start:
            spec_text = rest[start:end + 1]
            consumed = end + 1
    if not spec_text:
        return None, "", ""
    try:
        spec = json.loads(spec_text)
    except Exception:
        return None, "", ""
    if not isinstance(spec, dict):
        return None, "", ""
    after = rest[consumed:].strip()
    return spec, before, after


def _size_for(spec: dict[str, Any]) -> str:
    raw_size = str(spec.get("size") or "").strip().lower()
    if re.fullmatch(r"\d{3,4}x\d{3,4}", raw_size):
        return raw_size
    ratio = str(spec.get("aspect_ratio") or spec.get("ratio") or "").strip()
    return {
        "1:1": "1024x1024",
        "16:9": "1536x1024",
        "9:16": "1024x1536",
        "4:3": "1536x1024",
        "3:4": "1024x1536",
        "3:2": "1536x1024",
        "2:3": "1024x1536",
    }.get(ratio, "1024x1024")


def _image_from_json(payload: Any) -> tuple[str | None, str | None]:
    """Достаёт base64 или url из ответа провайдера."""
    if not isinstance(payload, dict):
        return None, None
    item: Any = None
    for key in ("data", "images", "output", "result"):
        raw = payload.get(key)
        if isinstance(raw, list) and raw:
            item = raw[0]
            break
        if isinstance(raw, dict):
            item = raw
            break
        if isinstance(raw, str):
            item = raw
            break
    if isinstance(item, str):
        if item.startswith("http"):
            return None, item
        return item, None
    if not isinstance(item, dict):
        return None, None
    b64 = item.get("b64_json") or item.get("b64") or item.get("image_base64") or item.get("base64")
    url = item.get("url") or item.get("image_url")
    return (str(b64) if b64 else None), (str(url) if url else None)


async def _download_image(url: str) -> bytes | None:
    try:
        timeout = aiohttp.ClientTimeout(total=90, sock_connect=20, sock_read=90)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(f"image download status={resp.status}")
                    return None
                return await resp.read()
    except Exception as e:
        logger.warning(f"image download fail: {e}")
        return None


async def _ticker(progress_cb: Callable[[int], Awaitable[None]] | None) -> None:
    pct = 4
    while True:
        await asyncio.sleep(2)
        if pct >= 95:
            continue
        pct = min(95, pct + random.randint(4, 9))
        if progress_cb:
            try:
                await progress_cb(pct)
            except Exception:
                pass


async def generate_image(
    spec: dict[str, Any],
    refs: list[bytes] | None = None,
    progress_cb: Callable[[int], Awaitable[None]] | None = None,
) -> bytes | None:
    """Генерирует или редактирует изображение. Модель фиксирована внутри."""
    if not ETAGEONE_API_KEY:
        raise RuntimeError("image provider key is missing")

    prompt = str(spec.get("prompt") or spec.get("description") or "").strip()
    if not prompt:
        raise RuntimeError("empty image prompt")
    prompt = prompt[:4000]
    size = _size_for(spec)
    images = dedupe_refs(list(refs or []), limit=4)

    ticker_task: asyncio.Task[None] | None = None
    if progress_cb:
        ticker_task = asyncio.create_task(_ticker(progress_cb))

    headers = {"Authorization": f"Bearer {ETAGEONE_API_KEY}"}
    timeout = aiohttp.ClientTimeout(total=240, sock_connect=20, sock_read=240)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if images:
                form = aiohttp.FormData()
                form.add_field("model", IMAGE_MODEL)
                form.add_field("prompt", prompt)
                form.add_field("n", "1")
                form.add_field("size", size)
                form.add_field("response_format", "b64_json")
                field = "image" if len(images) == 1 else "image[]"
                for idx, raw in enumerate(images):
                    form.add_field(
                        field, raw,
                        filename=f"ref{idx}.png",
                        content_type="image/png",
                    )
                async with session.post(
                    f"{IMAGE_API_BASE}/images/edits",
                    data=form, headers=headers,
                ) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        logger.warning(f"image edit status={resp.status}: {body[:500]}")
                        raise RuntimeError("image provider rejected the request")
                    payload = json.loads(body)
            else:
                payload_req = {
                    "model": IMAGE_MODEL,
                    "prompt": prompt,
                    "n": 1,
                    "size": size,
                    "response_format": "b64_json",
                }
                async with session.post(
                    f"{IMAGE_API_BASE}/images/generations",
                    json=payload_req, headers=headers,
                ) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        logger.warning(f"image gen status={resp.status}: {body[:500]}")
                        raise RuntimeError("image provider rejected the request")
                    payload = json.loads(body)
    finally:
        if ticker_task:
            ticker_task.cancel()
            try:
                await ticker_task
            except (asyncio.CancelledError, Exception):
                pass

    b64, url = _image_from_json(payload)
    if b64:
        try:
            return base64.b64decode(b64, validate=False)
        except Exception as e:
            logger.warning(f"image b64 decode: {e}")
            return None
    if url:
        return await _download_image(url)
    logger.warning("image provider returned no image")
    return None


# Загружаем состояние при импорте.
_load_usage()
