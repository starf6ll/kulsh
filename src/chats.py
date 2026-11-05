# Kulsh GPT | реестр чатов, в которых бот уже появлялся.
#
# Нужен для двух вещей: отправлять сообщения в конкретный чат по названию
# (межчатовые) и писать самостоятельно во все группы/серверы, а не только
# в один захардкоженный чат.

from __future__ import annotations

import json
import os
import time
from typing import Any

from src.util import DATA_DIR, logger

CHATS_FILE = os.path.join(DATA_DIR, "agent_chats.json")

_chats: dict[str, dict[str, Any]] = {}


def _load() -> None:
    global _chats
    try:
        if os.path.isfile(CHATS_FILE):
            with open(CHATS_FILE, encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                _chats = {str(k): v for k, v in data.items() if isinstance(v, dict)}
    except Exception as exc:
        logger.warning(f"chats load: {exc}")


def _save() -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(CHATS_FILE, "w", encoding="utf-8") as handle:
            json.dump(_chats, handle, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.warning(f"chats save: {exc}")


def _key(platform: str, chat_id: int) -> str:
    return f"{platform}:{int(chat_id)}"


def register(platform: str, chat_id: int, kind: str, title: str = "",
             guild_id: int | None = None, owner_id: int | None = None) -> None:
    """Запомнить чат. kind: private / group / channel."""
    if not chat_id:
        return
    key = _key(platform, chat_id)
    entry = _chats.setdefault(key, {})
    entry.update({
        "platform": platform,
        "id": int(chat_id),
        "kind": kind,
        "title": (title or entry.get("title") or str(chat_id))[:160],
        "seen": int(time.time()),
    })
    if guild_id:
        entry["guild_id"] = int(guild_id)
    if owner_id:
        entry["owner_id"] = int(owner_id)
    _save()


def get(platform: str, chat_id: int) -> dict[str, Any] | None:
    return _chats.get(_key(platform, chat_id))


def is_group(platform: str, chat_id: int) -> bool:
    entry = get(platform, chat_id)
    if entry:
        return entry.get("kind") in ("group", "channel")
    # Чат ещё не попадал в реестр: в Telegram id групп отрицательные,
    # в Discord канал-снежинка не бывает личкой без записи в реестре.
    return platform == "tg" and int(chat_id) < 0


def all_chats() -> list[dict[str, Any]]:
    return list(_chats.values())


def group_chats(platform: str) -> list[dict[str, Any]]:
    return [entry for entry in _chats.values()
            if entry.get("platform") == platform and entry.get("kind") in ("group", "channel")]


def find(platform: str, query: str) -> list[dict[str, Any]]:
    """Найти группу/канал по названию (точное совпадение важнее частичного)."""
    query = query.strip().lstrip("@").casefold()
    if not query:
        return []
    exact: list[dict[str, Any]] = []
    partial: list[dict[str, Any]] = []
    for entry in _chats.values():
        if entry.get("platform") != platform:
            continue
        if entry.get("kind") not in ("group", "channel"):
            continue
        title = str(entry.get("title") or "").casefold()
        if not title:
            continue
        if query == title:
            exact.append(entry)
        elif query in title:
            partial.append(entry)
    return exact or partial


_load()
