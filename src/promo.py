# Kulsh GPT | v2.51.0
# by (main author): starf6ll
# coauthor & bot hosting: pomidorka1515

"""Promo codes: fixed balance credit or a percent bonus on the next top-up."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from src import cloud
from src.billing import add_credit, get_balance, set_topup_bonus
from src.util import logger, PROMO_FILE

CODE_RE = re.compile(r"^[A-Z0-9_-]{3,24}$")

_cache: dict[str, dict[str, Any]] = {}


def _load_local() -> dict[str, dict[str, Any]]:
    try:
        if os.path.isfile(PROMO_FILE):
            with open(PROMO_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {str(k).upper(): v for k, v in data.items() if isinstance(v, dict)}
    except Exception as e:
        logger.warning(f"{PROMO_FILE} load: {e}")
    return {}


def _save_local(data: dict[str, dict[str, Any]]) -> None:
    try:
        with open(PROMO_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"{PROMO_FILE} save: {e}")


def normalize(code: str) -> str:
    return re.sub(r"\s+", "", (code or "")).upper()


def _get(code: str) -> dict[str, Any] | None:
    code = normalize(code)
    if not code:
        return None
    if cloud.enabled():
        return cloud.promo_get(code)
    return _load_local().get(code)


def _put(code: str, item: dict[str, Any]) -> None:
    code = normalize(code)
    if cloud.enabled():
        cloud.promo_put(code, item)
        return
    data = _load_local()
    data[code] = item
    _save_local(data)


def _delete(code: str) -> None:
    code = normalize(code)
    if cloud.enabled():
        cloud.promo_delete(code)
        cloud._cmd("DEL", f"kulsh:promo:{code}:used")
        return
    data = _load_local()
    data.pop(code, None)
    _save_local(data)


def _used_count(code: str) -> int:
    if cloud.enabled():
        return cloud.promo_use_count(code)
    return int((_get(code) or {}).get("used") or 0)


def _was_used(code: str, acct: str) -> bool:
    if cloud.enabled():
        return cloud.promo_used(code, acct)
    used_by = (_get(code) or {}).get("usedBy") or []
    return acct in used_by


def _mark_used(code: str, acct: str) -> None:
    if cloud.enabled():
        cloud.promo_mark_used(code, acct)
        return
    item = _get(code) or {}
    used_by = item.get("usedBy") if isinstance(item.get("usedBy"), list) else []
    used_by.append(acct)
    item["usedBy"] = used_by
    item["used"] = len(used_by)
    _put(code, item)


def list_promos() -> list[dict[str, Any]]:
    if cloud.enabled():
        items = cloud.promo_list()
    else:
        items = [dict(v, code=k) for k, v in _load_local().items()]
    for item in items:
        code = str(item.get("code") or "")
        item["activations"] = _used_count(code)
    return sorted(items, key=lambda x: int(x.get("createdAt") or 0), reverse=True)


def create_promo(code: str, kind: str, value: int, uses: int = 0,
                 expires_at: int = 0) -> tuple[bool, str]:
    code = normalize(code)
    if not CODE_RE.match(code):
        return False, "Код: 3-24 символа, латиница, цифры, - и _."
    if kind not in ("amount", "bonus"):
        return False, "Тип: amount (деньги) или bonus (процент)."
    if value <= 0:
        return False, "Значение должно быть больше нуля."
    if kind == "bonus" and value > 500:
        return False, "Бонус больше 500% — перебор."
    if _get(code):
        return False, "Такой код уже есть."
    item = {
        "type": kind,
        "value": int(value),
        "uses": max(0, int(uses)),
        "expiresAt": int(expires_at),
        "createdAt": int(time.time()),
        "active": True,
    }
    _put(code, item)
    logger.info(f"promo: created {code} ({kind} {value}, uses={uses})")
    return True, code


def set_active(code: str, active: bool) -> bool:
    item = _get(code)
    if not item:
        return False
    item["active"] = bool(active)
    _put(code, item)
    return True


def delete_promo(code: str) -> bool:
    if not _get(code):
        return False
    _delete(code)
    return True


def redeem(platform: str, user_id: int, code: str) -> tuple[str, str]:
    """Returns (status, detail). Status: ok_amount / ok_bonus / error."""
    code = normalize(code)
    item = _get(code)
    if not item:
        return "error", "Такого промокода нет."
    if not item.get("active", True):
        return "error", "Промокод отключён."
    expires = int(item.get("expiresAt") or 0)
    if expires and time.time() > expires:
        return "error", "Срок действия промокода истёк."
    acct = cloud.resolve(platform, user_id)
    if _was_used(code, acct):
        return "error", "Ты уже активировал этот промокод."
    uses = int(item.get("uses") or 0)
    if uses and _used_count(code) >= uses:
        return "error", "Лимит активаций промокода исчерпан."
    kind = str(item.get("type") or "")
    value = int(item.get("value") or 0)
    if kind == "amount":
        add_credit(platform, user_id, float(value), note=f"promo:{code}")
        _mark_used(code, acct)
        return "ok_amount", f"+{value} ₽ на баланс. Сейчас на счёте {get_balance(platform, user_id):.2f} ₽."
    if kind == "bonus":
        current = cloud.get_bonus(acct)
        set_topup_bonus(platform, user_id, max(current, value))
        _mark_used(code, acct)
        return "ok_bonus", f"Бонус +{value}% к следующему пополнению. Сработает автоматически."
    return "error", "Промокод повреждён."