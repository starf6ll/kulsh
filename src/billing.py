# Kulsh GPT | v2.48.0
# by (main author): starfall-apk
# coauthor & bot hosting: pomidorko1515

"""Balance, DonationAlerts top-ups, support tickets and profile data."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any

import aiohttp

from src.util import (
    DONATIONALERTS_TOKEN,
    JsonDict,
    logger,
)

BALANCES_FILE = 'balances.json'
DONATIONS_FILE = 'da_processed.json'
TICKETS_FILE = 'support_tickets.json'
DA_TOKEN_FILE = 'da_token.json'

DONATIONALERTS_API = "https://www.donationalerts.com/api/v1"
DONATIONALERTS_OAUTH = "https://www.donationalerts.com/oauth/token"
MIN_TOPUP_RUB = 80.0
TOPUP_CURRENCY = os.getenv("DONATIONALERTS_CURRENCY") or "RUB"
DONATIONALERTS_PAGE = os.getenv("DONATIONALERTS_PAGE") or ""

# Ссылки на юридические документы (публикуются через telegra.ph).
TERMS_URL = os.getenv("KULSH_TERMS_URL") or "https://telegra.ph/Kulsh-AI--Polzovatelskoe-soglashenie-10-17"
PRIVACY_URL = os.getenv("KULSH_PRIVACY_URL") or "https://telegra.ph/Kulsh-AI--Politika-konfidencialnosti-10-17-2"

SUPPORT_ADMIN_TG = int(os.getenv("SUPPORT_ADMIN_TG") or "1420898868")
SUPPORT_ADMIN_DS = int(os.getenv("SUPPORT_ADMIN_DS") or "0")


def _load(path: str, default: Any) -> Any:
    try:
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"{path} load fail: {e}")
    return default


def _save(path: str, data: Any) -> None:
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"{path} save fail: {e}")


balances: dict[str, JsonDict] = _load(BALANCES_FILE, {})
_processed_donations: set[int] = set(int(x) for x in _load(DONATIONS_FILE, []))
tickets: JsonDict = _load(TICKETS_FILE, {"next_id": 1, "items": {}, "admin_map": {}})
tickets.setdefault("next_id", 1)
tickets.setdefault("items", {})
tickets.setdefault("admin_map", {})
_da_token: JsonDict = _load(DA_TOKEN_FILE, {})


# ============================================================
# BALANCE
# ============================================================
def _bkey(platform: str, user_id: int) -> str:
    return f"{platform}_{user_id}"


def get_balance(platform: str, user_id: int) -> float:
    entry = balances.get(_bkey(platform, user_id)) or {}
    return round(float(entry.get("balance") or 0.0), 2)


def get_total_topup(platform: str, user_id: int) -> float:
    entry = balances.get(_bkey(platform, user_id)) or {}
    return round(float(entry.get("total_topup") or 0.0), 2)


def get_topup_count(platform: str, user_id: int) -> int:
    entry = balances.get(_bkey(platform, user_id)) or {}
    history = entry.get("history")
    if not isinstance(history, list):
        return 0
    return sum(1 for item in history if isinstance(item, dict) and float(item.get("amount") or 0) > 0)


def add_balance(platform: str, user_id: int, amount_rub: float, note: str = "") -> float:
    if amount_rub <= 0:
        return get_balance(platform, user_id)
    key = _bkey(platform, user_id)
    entry = balances.setdefault(key, {"balance": 0.0, "total_topup": 0.0, "history": []})
    entry["balance"] = round(float(entry.get("balance") or 0.0) + amount_rub, 2)
    entry["total_topup"] = round(float(entry.get("total_topup") or 0.0) + amount_rub, 2)
    history = entry.setdefault("history", [])
    if isinstance(history, list):
        history.append({"ts": int(time.time()), "amount": round(amount_rub, 2), "note": note})
        del history[:-50]
    _save(BALANCES_FILE, balances)
    return entry["balance"]


def charge_balance(platform: str, user_id: int, amount_rub: float, note: str = "") -> bool:
    if amount_rub <= 0:
        return True
    key = _bkey(platform, user_id)
    entry = balances.setdefault(key, {"balance": 0.0, "total_topup": 0.0, "history": []})
    balance = float(entry.get("balance") or 0.0)
    if balance + 1e-9 < amount_rub:
        return False
    entry["balance"] = round(balance - amount_rub, 6)
    history = entry.setdefault("history", [])
    if isinstance(history, list):
        history.append({"ts": int(time.time()), "amount": -round(amount_rub, 6), "note": note})
        del history[:-50]
    _save(BALANCES_FILE, balances)
    return True


def has_balance_for_paid(platform: str, user_id: int) -> bool:
    return get_balance(platform, user_id) > 0.005


def topup_code(platform: str, user_id: int) -> str:
    return f"ID{user_id}"


# ============================================================
# DONATIONALERTS
# ============================================================
async def _da_access_token() -> str:
    token = _da_token.get("access_token") or DONATIONALERTS_TOKEN
    if token:
        return str(token)
    refresh = _da_token.get("refresh_token") or os.getenv("DONATIONALERTS_REFRESH_TOKEN")
    client_id = os.getenv("DONATIONALERTS_CLIENT_ID")
    client_secret = os.getenv("DONATIONALERTS_CLIENT_SECRET")
    if not (refresh and client_id and client_secret):
        return ""
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "oauth-donation-index",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(DONATIONALERTS_OAUTH, data=payload,
                                    timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    logger.warning(f"DA refresh {resp.status}: {(await resp.text())[:200]}")
                    return ""
                data = await resp.json()
        _da_token.update(data)
        _save(DA_TOKEN_FILE, _da_token)
        return str(data.get("access_token") or "")
    except Exception as e:
        logger.warning(f"DA refresh fail: {e}")
        return ""


def _amount_to_rub(amount: float, currency: str) -> float:
    currency = (currency or TOPUP_CURRENCY).upper()
    if currency in ("RUB", "RUR"):
        return float(amount)
    if currency == "USD":
        return float(amount) * 90.0
    if currency == "EUR":
        return float(amount) * 98.0
    if currency == "UAH":
        return float(amount) * 2.2
    if currency == "KZT":
        return float(amount) * 0.18
    return float(amount)


def _parse_code(message: str) -> int | None:
    m = re.search(r'(?i)\bID\s*[:#]?\s*(\d{5,25})\b', message or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


async def poll_donations_once() -> list[tuple[str, int, float, str]]:
    """Проверяет новые донаты и зачисляет их. Возвращает список зачислений."""
    token = await _da_access_token()
    if not token:
        return []
    url = f"{DONATIONALERTS_API}/alerts/donations"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    logger.warning(f"DA donations {resp.status}: {(await resp.text())[:200]}")
                    return []
                data = await resp.json()
    except Exception as e:
        logger.warning(f"DA poll fail: {e}")
        return []

    items = data.get("data") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []

    credited: list[tuple[str, int, float, str]] = []
    changed = False
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            donation_id = int(item.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if donation_id and donation_id in _processed_donations:
            continue
        message = str(item.get("message") or "")
        user_id = _parse_code(message)
        if user_id is None:
            continue
        try:
            amount = _amount_to_rub(float(item.get("amount") or 0), str(item.get("currency") or ""))
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue

        # Код содержит числовой id. Пробуем оба платформенных ключа.
        platform = "tg"
        if user_id >= 10**15 or balances.get(_bkey("ds", user_id)):
            platform = "ds"
        add_balance(platform, user_id, amount, note=f"donationalerts:{donation_id}")
        credited.append((platform, user_id, amount, str(item.get("username") or "")))
        if donation_id:
            _processed_donations.add(donation_id)
            changed = True
        logger.info(f"💰 Донат {amount:.2f} ₽ → {platform}_{user_id} (#{donation_id})")

    if changed:
        _save(DONATIONS_FILE, sorted(_processed_donations))
    return credited


async def donation_poll_loop(interval: int = 60) -> None:
    while True:
        try:
            await poll_donations_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"donation loop: {e}")
        await asyncio.sleep(interval)


# ============================================================
# SUPPORT TICKETS
# ============================================================
def create_ticket(platform: str, user_id: int, chat_id: int, text: str) -> int:
    tid = int(tickets.get("next_id") or 1)
    tickets["next_id"] = tid + 1
    tickets["items"][str(tid)] = {
        "platform": platform,
        "user_id": user_id,
        "chat_id": chat_id,
        "status": "open",
        "created": int(time.time()),
        "messages": [{"role": "user", "text": text, "ts": int(time.time())}],
    }
    _save(TICKETS_FILE, tickets)
    return tid


def get_ticket(tid: int) -> JsonDict | None:
    item = tickets.get("items", {}).get(str(tid))
    return item if isinstance(item, dict) else None


def append_ticket_message(tid: int, role: str, text: str) -> None:
    item = get_ticket(tid)
    if not item:
        return
    msgs = item.setdefault("messages", [])
    if isinstance(msgs, list):
        msgs.append({"role": role, "text": text, "ts": int(time.time())})
    if role == "support":
        item["status"] = "answered"
    _save(TICKETS_FILE, tickets)


def map_admin_message(platform: str, message_id: int, tid: int) -> None:
    tickets.setdefault("admin_map", {})[f"{platform}_{message_id}"] = tid
    _save(TICKETS_FILE, tickets)


def ticket_by_admin_message(platform: str, message_id: int) -> int | None:
    try:
        return int(tickets.get("admin_map", {}).get(f"{platform}_{message_id}"))
    except (TypeError, ValueError):
        return None


def close_ticket(tid: int) -> None:
    item = get_ticket(tid)
    if item:
        item["status"] = "closed"
        _save(TICKETS_FILE, tickets)
