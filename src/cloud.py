# Kulsh GPT | v2.51.0
# by (main author): starfall-apk
# coauthor & bot hosting: pomidorka1515

"""Shared account storage in Upstash Redis (the same database the website uses).

The bot and the site keep one source of truth:
  kulsh:acct:{id}            -> JSON account (linked identities, names)
  kulsh:ident:{identity}     -> account id
  kulsh:merged:{old}         -> new account id (after a merge)
  kulsh:u:{id}:balance       -> balance in kopecks
  kulsh:u:{id}:topup         -> total topped up in kopecks
  kulsh:u:{id}:topupcount    -> number of top-ups
  kulsh:u:{id}:bonus         -> one-time top-up bonus percent
  kulsh:u:{id}:usage:{day}   -> daily tokens (written by the website)
  kulsh:u:{id}:apikeys       -> JSON list of API keys
  kulsh:key:{sha256}         -> account id
  kulsh:link:{code}          -> pending bot <-> site link (TTL 15 min)

Every call is a small synchronous REST request. Reads are cached for a few
seconds so hot paths (billing on every AI answer) don't hammer Redis.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from src.util import logger, CLOUD_MIGRATED_FILE

CLOUD_URL = (os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
CLOUD_TOKEN = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""

_READ_TTL = 4.0
_cache: dict[str, tuple[Any, float]] = {}
_breaker_until = 0.0
_fail_streak = 0

ACCOUNT_PREFIX = "kulsh:acct:"
IDENT_PREFIX = "kulsh:ident:"
MERGED_PREFIX = "kulsh:merged:"
BALANCE_PREFIX = "kulsh:u:"
KEY_PREFIX = "kulsh:key:"
LINK_PREFIX = "kulsh:link:"
PROMO_PREFIX = "kulsh:promo:"
PROMO_SET = "kulsh:promos"


def enabled() -> bool:
    return bool(CLOUD_URL and CLOUD_TOKEN)


def _request(path: str, body: Any) -> Any:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        CLOUD_URL + path,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {CLOUD_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _cmd(*args: Any) -> Any:
    """One Redis command. Returns None when the cloud is off or unreachable."""
    global _breaker_until, _fail_streak
    if not enabled():
        return None
    if time.time() < _breaker_until:
        return None
    try:
        out = _request("", list(args))
        _fail_streak = 0
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        _fail_streak += 1
        if _fail_streak >= 3:
            _breaker_until = time.time() + 60
            logger.warning(f"cloud: недоступен, пауза 60 с ({e})")
        else:
            logger.warning(f"cloud {args[0]}: {e}")
        return None
    if isinstance(out, dict):
        if out.get("error"):
            logger.warning(f"cloud {args[0]}: {out['error']}")
            return None
        return out.get("result")
    return out


def _pipeline(cmds: list[list[Any]]) -> list[Any]:
    global _breaker_until, _fail_streak
    if not enabled() or not cmds:
        return []
    if time.time() < _breaker_until:
        return []
    try:
        out = _request("/pipeline", cmds)
        _fail_streak = 0
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        _fail_streak += 1
        if _fail_streak >= 3:
            _breaker_until = time.time() + 60
        logger.warning(f"cloud pipeline: {e}")
        return []
    if not isinstance(out, list):
        return []
    result: list[Any] = []
    for item in out:
        if isinstance(item, dict) and item.get("error"):
            logger.warning(f"cloud pipeline: {item['error']}")
            result.append(None)
        else:
            result.append(item.get("result") if isinstance(item, dict) else None)
    return result


def _cache_get(key: str) -> Any | None:
    hit = _cache.get(key)
    if not hit:
        return None
    value, ts = hit
    if time.time() - ts > _READ_TTL:
        _cache.pop(key, None)
        return None
    return value


def _cache_peek(key: str) -> Any | None:
    """Последнее известное значение без учёта TTL — на случай короткого сбоя Redis."""
    hit = _cache.get(key)
    return hit[0] if hit else None


def _cache_set(key: str, value: Any) -> None:
    _cache[key] = (value, time.time())


def _cache_drop(*keys: str) -> None:
    for key in keys:
        _cache.pop(key, None)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json(value: Any, default: Any) -> Any:
    if not value:
        return default
    try:
        parsed = json.loads(value)
        return parsed
    except (TypeError, ValueError):
        return default


# ============================================================
# ACCOUNTS
# ============================================================
def identity(platform: str, user_id: int | str) -> str:
    """Identity key. Website Telegram logins use the same `tg:` namespace."""
    return f"{platform}:{user_id}"


def _follow(acct: str | None) -> str | None:
    """Follows merge redirects so old sessions keep working."""
    seen = 0
    while acct and seen < 4:
        nxt = _cmd("GET", MERGED_PREFIX + acct)
        if not nxt:
            return acct
        acct = str(nxt)
        seen += 1
    return acct


def resolve(platform: str, user_id: int | str) -> str:
    """Account id for a platform user, creating the account on first use."""
    ident = identity(platform, user_id)
    if not enabled():
        return ident
    cached = _cache_get(f"ident:{ident}")
    if cached:
        return str(cached)
    acct = _follow(_cmd("GET", IDENT_PREFIX + ident))
    if not acct:
        acct = ident
        _cmd("SET", IDENT_PREFIX + ident, acct, "NX")
        _ensure_account(acct, ident)
    _cache_set(f"ident:{ident}", acct)
    return acct


def identity_exists(platform: str, user_id: int | str) -> bool:
    if not enabled():
        return False
    return bool(_cmd("GET", IDENT_PREFIX + identity(platform, user_id)))


def resolve_identity(ident: str) -> str | None:
    """Account id for an already-normalized identity (used by the website)."""
    if not enabled():
        return ident
    acct = _follow(_cmd("GET", IDENT_PREFIX + ident))
    if acct:
        return str(acct)
    _cmd("SET", IDENT_PREFIX + ident, ident, "NX")
    _ensure_account(ident, ident)
    return ident


def _ensure_account(acct: str, ident: str) -> None:
    record = {
        "id": acct,
        "createdAt": int(time.time() * 1000),
        "ids": [ident],
        "names": {},
    }
    _cmd("SET", ACCOUNT_PREFIX + acct, json.dumps(record, ensure_ascii=False), "NX")


def account_record(acct: str) -> dict[str, Any]:
    raw = _cmd("GET", ACCOUNT_PREFIX + acct)
    data = _json(raw, None)
    if isinstance(data, dict):
        return data
    return {"id": acct, "createdAt": 0, "ids": [acct], "names": {}}


def account_ids(acct: str) -> list[str]:
    record = account_record(acct)
    ids = record.get("ids")
    return [str(x) for x in ids] if isinstance(ids, list) else [acct]


def set_name(acct: str, platform: str, name: str) -> None:
    if not enabled() or not name:
        return
    record = account_record(acct)
    names = record.get("names")
    if not isinstance(names, dict):
        names = {}
    names[platform] = str(name)[:64]
    record["names"] = names
    _cmd("SET", ACCOUNT_PREFIX + acct, json.dumps(record, ensure_ascii=False))


def display_name(acct: str) -> str:
    names = account_record(acct).get("names")
    if isinstance(names, dict):
        for value in names.values():
            if value:
                return str(value)
    return acct


def merge_accounts(src: str, dst: str) -> dict[str, Any]:
    """Moves everything from `src` into `dst`. Returns a summary for the warning."""
    src = _follow(src) or src
    dst = _follow(dst) or dst
    if src == dst:
        return {"merged": False, "balance": get_balance_kop(dst), "accounts": 1}
    src_balance = get_balance_kop(src)
    dst_balance = get_balance_kop(dst)
    src_topup = _int(_cmd("GET", f"{BALANCE_PREFIX}{src}:topup"))
    dst_topup = _int(_cmd("GET", f"{BALANCE_PREFIX}{dst}:topup"))
    src_count = _int(_cmd("GET", f"{BALANCE_PREFIX}{src}:topupcount"))
    dst_count = _int(_cmd("GET", f"{BALANCE_PREFIX}{dst}:topupcount"))
    src_bonus = _int(_cmd("GET", f"{BALANCE_PREFIX}{src}:bonus"))
    dst_bonus = _int(_cmd("GET", f"{BALANCE_PREFIX}{dst}:bonus"))

    src_keys = list_api_keys(src)
    dst_keys = list_api_keys(dst)
    seen = {str(k.get("id")) for k in dst_keys}
    merged_keys = dst_keys + [k for k in src_keys if str(k.get("id")) not in seen]
    merged_keys = merged_keys[:10]

    src_record = account_record(src)
    dst_record = account_record(dst)
    src_ids = account_ids(src)
    dst_ids = account_ids(dst)
    all_ids = dst_ids + [i for i in src_ids if i not in dst_ids]
    names = dst_record.get("names") if isinstance(dst_record.get("names"), dict) else {}
    src_names = src_record.get("names") if isinstance(src_record.get("names"), dict) else {}
    for k, v in src_names.items():
        names.setdefault(k, v)
    dst_record["ids"] = all_ids
    dst_record["names"] = names
    dst_record["createdAt"] = min(
        _int(dst_record.get("createdAt")), _int(src_record.get("createdAt")) or _int(dst_record.get("createdAt"))
    )

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    src_usage = _int(_cmd("GET", f"{BALANCE_PREFIX}{src}:usage:{today}"))
    dst_usage = _int(_cmd("GET", f"{BALANCE_PREFIX}{dst}:usage:{today}"))

    cmds: list[list[Any]] = [
        ["SET", f"{BALANCE_PREFIX}{dst}:balance", str(src_balance + dst_balance)],
        ["SET", f"{BALANCE_PREFIX}{dst}:topup", str(src_topup + dst_topup)],
        ["SET", f"{BALANCE_PREFIX}{dst}:topupcount", str(src_count + dst_count)],
        ["SET", f"{BALANCE_PREFIX}{dst}:usage:{today}", str(max(src_usage, dst_usage))],
        ["SET", f"{BALANCE_PREFIX}{dst}:apikeys", json.dumps(merged_keys, ensure_ascii=False)],
        ["SET", ACCOUNT_PREFIX + dst, json.dumps(dst_record, ensure_ascii=False)],
        ["SET", MERGED_PREFIX + src, dst],
        ["DEL", ACCOUNT_PREFIX + src],
        ["DEL", f"{BALANCE_PREFIX}{src}:balance"],
        ["DEL", f"{BALANCE_PREFIX}{src}:topup"],
        ["DEL", f"{BALANCE_PREFIX}{src}:topupcount"],
        ["DEL", f"{BALANCE_PREFIX}{src}:bonus"],
        ["DEL", f"{BALANCE_PREFIX}{src}:apikeys"],
        ["DEL", f"{BALANCE_PREFIX}{src}:usage:{today}"],
    ]
    if max(src_bonus, dst_bonus):
        cmds.append(["SET", f"{BALANCE_PREFIX}{dst}:bonus", str(max(src_bonus, dst_bonus))])
    for ident in all_ids:
        cmds.append(["SET", IDENT_PREFIX + ident, dst])
    for key in src_keys:
        h = str(key.get("hash") or "")
        if h:
            cmds.append(["SET", KEY_PREFIX + h, dst])
    _pipeline(cmds)
    _cache_drop(
        f"bal:{dst}", f"bal:{src}", f"topup:{dst}", f"topup:{src}",
        f"count:{dst}", f"count:{src}", f"keys:{dst}", f"keys:{src}",
    )
    logger.info(f"cloud: merged {src} -> {dst} ({src_balance + dst_balance} kop)")
    return {
        "merged": True,
        "from": src,
        "into": dst,
        "balance": src_balance + dst_balance,
        "added": src_balance,
    }


# ============================================================
# BALANCE
# ============================================================
def get_balance_kop(acct: str) -> int:
    if not enabled():
        return 0
    cached = _cache_get(f"bal:{acct}")
    if cached is not None:
        return int(cached)
    raw = _cmd("GET", f"{BALANCE_PREFIX}{acct}:balance")
    if raw is None:
        stale = _cache_peek(f"bal:{acct}")
        return int(stale) if stale is not None else 0
    value = _int(raw)
    _cache_set(f"bal:{acct}", value)
    return value


def add_balance_kop(acct: str, kop: int, *, topup: bool = False) -> int:
    if not enabled() or kop <= 0:
        return get_balance_kop(acct)
    cmds: list[list[Any]] = [["INCRBY", f"{BALANCE_PREFIX}{acct}:balance", str(kop)]]
    if topup:
        cmds.append(["INCRBY", f"{BALANCE_PREFIX}{acct}:topup", str(kop)])
        cmds.append(["INCRBY", f"{BALANCE_PREFIX}{acct}:topupcount", "1"])
    _pipeline(cmds)
    _cache_drop(f"bal:{acct}", f"topup:{acct}", f"count:{acct}")
    return get_balance_kop(acct)


def charge_kop(acct: str, kop: int) -> bool:
    if kop <= 0:
        return True
    if not enabled():
        return False
    script = (
        "local b=tonumber(redis.call('GET',KEYS[1]) or '0') "
        "local a=tonumber(ARGV[1]) "
        "if b>=a then redis.call('DECRBY',KEYS[1],a) return 1 else return 0 end"
    )
    out = _cmd("EVAL", script, "1", f"{BALANCE_PREFIX}{acct}:balance", str(kop))
    _cache_drop(f"bal:{acct}")
    return str(out) == "1"


def get_total_topup_kop(acct: str) -> int:
    if not enabled():
        return 0
    cached = _cache_get(f"topup:{acct}")
    if cached is not None:
        return int(cached)
    raw = _cmd("GET", f"{BALANCE_PREFIX}{acct}:topup")
    if raw is None:
        stale = _cache_peek(f"topup:{acct}")
        return int(stale) if stale is not None else 0
    value = _int(raw)
    _cache_set(f"topup:{acct}", value)
    return value


def get_topup_count(acct: str) -> int:
    if not enabled():
        return 0
    cached = _cache_get(f"count:{acct}")
    if cached is not None:
        return int(cached)
    value = _int(_cmd("GET", f"{BALANCE_PREFIX}{acct}:topupcount"))
    _cache_set(f"count:{acct}", value)
    return value


def get_bonus(acct: str) -> int:
    if not enabled():
        return 0
    return _int(_cmd("GET", f"{BALANCE_PREFIX}{acct}:bonus"))


def set_bonus(acct: str, percent: int) -> None:
    if not enabled():
        return
    if percent > 0:
        _cmd("SET", f"{BALANCE_PREFIX}{acct}:bonus", str(int(percent)))
    else:
        _cmd("DEL", f"{BALANCE_PREFIX}{acct}:bonus")


def consume_bonus(acct: str) -> int:
    """Returns and clears the pending top-up bonus percent."""
    if not enabled():
        return 0
    value = get_bonus(acct)
    if value:
        _cmd("DEL", f"{BALANCE_PREFIX}{acct}:bonus")
    return value


# ============================================================
# USAGE
# ============================================================
def usage(acct: str) -> dict[str, Any]:
    """Daily tokens from the website. The bot only displays this."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    used = _int(_cmd("GET", f"{BALANCE_PREFIX}{acct}:usage:{day}")) if enabled() else 0
    return {"used": used, "limit": 100000, "day": day}


# ============================================================
# API KEYS
# ============================================================
def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _new_key() -> str:
    raw = base64.urlsafe_b64encode(secrets.token_bytes(24)).decode("ascii").rstrip("=")
    return "kulsh_sk_" + raw


def list_api_keys(acct: str) -> list[dict[str, Any]]:
    if not enabled():
        return []
    cached = _cache_get(f"keys:{acct}")
    if cached is not None:
        return list(cached)
    data = _json(_cmd("GET", f"{BALANCE_PREFIX}{acct}:apikeys"), [])
    keys = [k for k in data if isinstance(k, dict)] if isinstance(data, list) else []
    _cache_set(f"keys:{acct}", keys)
    return keys


def _public_key(key: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": key.get("id"),
        "name": key.get("name"),
        "prefix": key.get("prefix"),
        "createdAt": key.get("createdAt") or 0,
        "lastUsed": key.get("lastUsed") or 0,
    }


def create_api_key(acct: str, name: str = "Ключ") -> dict[str, Any] | None:
    if not enabled():
        return None
    keys = list_api_keys(acct)
    if len(keys) >= 10:
        return {"error": "limit"}
    raw = _new_key()
    digest = _hash_key(raw)
    record = {
        "id": "k_" + secrets.token_hex(4),
        "name": (str(name or "Ключ").strip()[:40] or "Ключ"),
        "prefix": raw[:14] + "…",
        "hash": digest,
        "createdAt": int(time.time() * 1000),
        "lastUsed": 0,
    }
    next_keys = [record, *keys]
    _pipeline([
        ["SET", f"{BALANCE_PREFIX}{acct}:apikeys", json.dumps(next_keys, ensure_ascii=False)],
        ["SET", KEY_PREFIX + digest, acct],
    ])
    _cache_drop(f"keys:{acct}")
    return {"key": _public_key(record), "secret": raw}


def revoke_api_key(acct: str, key_id: str) -> bool:
    if not enabled():
        return False
    keys = list_api_keys(acct)
    target = next((k for k in keys if str(k.get("id")) == str(key_id)), None)
    if not target:
        return False
    next_keys = [k for k in keys if str(k.get("id")) != str(key_id)]
    cmds: list[list[Any]] = [
        ["SET", f"{BALANCE_PREFIX}{acct}:apikeys", json.dumps(next_keys, ensure_ascii=False)]
    ]
    if target.get("hash"):
        cmds.append(["DEL", KEY_PREFIX + str(target["hash"])])
    _pipeline(cmds)
    _cache_drop(f"keys:{acct}")
    return True


# ============================================================
# LINK CODES (bot -> website)
# ============================================================
def create_link_code(platform: str, user_id: int | str, ttl: int = 900,
                     name: str = "") -> str:
    code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
    ident = identity(platform, user_id)
    payload = {
        "identity": ident,
        "platform": platform,
        "userId": str(user_id),
        "name": (name or "")[:64],
        "ts": int(time.time()),
    }
    _cmd("SET", LINK_PREFIX + code, json.dumps(payload, ensure_ascii=False), "EX", str(ttl))
    return code


def read_link_code(code: str) -> dict[str, Any] | None:
    data = _json(_cmd("GET", LINK_PREFIX + code.upper()), None)
    return data if isinstance(data, dict) else None


def drop_link_code(code: str) -> None:
    _cmd("DEL", LINK_PREFIX + code.upper())


# ============================================================
# PROMO CODES (stored in the shared database)
# ============================================================
def promo_get(code: str) -> dict[str, Any] | None:
    data = _json(_cmd("GET", PROMO_PREFIX + code.upper()), None)
    return data if isinstance(data, dict) else None


def promo_put(code: str, data: dict[str, Any]) -> None:
    code = code.upper()
    _cmd("SET", PROMO_PREFIX + code, json.dumps(data, ensure_ascii=False))
    _cmd("SADD", PROMO_SET, code)


def promo_delete(code: str) -> None:
    code = code.upper()
    _cmd("DEL", PROMO_PREFIX + code)
    _cmd("SREM", PROMO_SET, code)


def promo_list() -> list[dict[str, Any]]:
    codes = _cmd("SMEMBERS", PROMO_SET) or []
    out: list[dict[str, Any]] = []
    if not isinstance(codes, list):
        return out
    for code in codes:
        item = promo_get(str(code))
        if item:
            item["code"] = str(code)
            out.append(item)
    return sorted(out, key=lambda x: int(x.get("createdAt") or 0), reverse=True)


def promo_used(code: str, acct: str) -> bool:
    return bool(_cmd("HEXISTS", f"{PROMO_PREFIX}{code.upper()}:used", acct))


def promo_mark_used(code: str, acct: str) -> None:
    _cmd("HSET", f"{PROMO_PREFIX}{code.upper()}:used", acct, str(int(time.time())))


def promo_use_count(code: str) -> int:
    return _int(_cmd("HLEN", f"{PROMO_PREFIX}{code.upper()}:used"))


# ============================================================
# MIGRATION OF THE OLD LOCAL balances.json
# ============================================================
# Путь вынесен в util (data/cloud_migrated.json), чтобы маркер миграции
# не сбрасывался при git pull / reset --hard.
MIGRATED_FILE = CLOUD_MIGRATED_FILE


def migrate_legacy(balances: dict[str, Any]) -> None:
    """Copies old bot balances into the shared database once."""
    if not enabled():
        return
    try:
        if os.path.isfile(MIGRATED_FILE):
            with open(MIGRATED_FILE, encoding="utf-8") as f:
                if int(json.load(f).get("v") or 0) >= 1:
                    return
    except Exception:
        pass
    moved = 0
    failed = False
    for key, entry in balances.items():
        if not isinstance(entry, dict):
            continue
        platform, _, tail = str(key).partition("_")
        if platform not in ("tg", "ds") or not tail.isdigit():
            continue
        acct = resolve(platform, int(tail))
        bal_kop = round(float(entry.get("balance") or 0) * 100)
        topup_kop = round(float(entry.get("total_topup") or 0) * 100)
        history = entry.get("history") if isinstance(entry.get("history"), list) else []
        count = sum(1 for item in history if isinstance(item, dict) and float(item.get("amount") or 0) > 0)
        cmds: list[list[Any]] = []
        if bal_kop and _cmd("GET", f"{BALANCE_PREFIX}{acct}:balance") is None:
            cmds.append(["SET", f"{BALANCE_PREFIX}{acct}:balance", str(bal_kop)])
        if topup_kop and _cmd("GET", f"{BALANCE_PREFIX}{acct}:topup") is None:
            cmds.append(["SET", f"{BALANCE_PREFIX}{acct}:topup", str(topup_kop)])
        if count and _cmd("GET", f"{BALANCE_PREFIX}{acct}:topupcount") is None:
            cmds.append(["SET", f"{BALANCE_PREFIX}{acct}:topupcount", str(count)])
        if cmds:
            out = _pipeline(cmds)
            if len(out) != len(cmds):
                failed = True
                break
            moved += 1
    if failed:
        logger.warning("cloud: миграция балансов не удалась — попробую при следующем запуске")
        return
    try:
        with open(MIGRATED_FILE, "w", encoding="utf-8") as f:
            json.dump({"v": 1, "moved": moved}, f)
    except Exception as e:
        logger.warning(f"cloud migration marker: {e}")
    if moved:
        logger.info(f"cloud: migrated {moved} local balances")