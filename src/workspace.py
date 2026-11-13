# Kulsh GPT | workspace
# by (main author): starf6ll
# coauthor & bot hosting: pomidorka1515

"""Изолированное рабочее пространство чата.

Бот хранит присланные файлы и картинки в отдельной папке на диске и умеет
работать с ними как агент: читать диапазоны строк, писать и патчить файлы,
собирать и распаковывать архивы, отправлять готовые файлы обратно и выполнять
безопасные терминальные команды. Никакого доступа за пределы workspace нет.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tarfile
import time
import zipfile
from typing import Any

from src.util import DATA_DIR, logger

WORKSPACE_ROOT = os.path.join(DATA_DIR, "workspace")
MAX_WORKSPACE_FILES = 200
MAX_WORKSPACE_BYTES = 32 * 1024 * 1024
MAX_READ_CHARS = 4000
WORKSPACE_TTL_SECONDS = 7 * 24 * 3600
# Медиа и присланные файлы живут на сервере недолго: их всегда можно заново
# скачать из Telegram по file_id. Сгенерированные файлы без копии в чате
# живут чуть дольше, чтобы модель успела их доработать.
MEDIA_TTL_SECONDS = 60
UPLOAD_TTL_SECONDS = 60
GENERATED_TTL_SECONDS = 600
INDEX_NAME = ".index.json"

_EXT_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "video/mp4": ".mp4",
    "application/pdf": ".pdf",
    "application/zip": ".zip",
}


def _chat_key(platform: str, chat_id: int) -> str:
    safe = re.sub(r"[^0-9A-Za-z_-]", "_", f"{platform}_{chat_id}")
    return safe or "chat"


def workspace_dir(platform: str, chat_id: int) -> str:
    """Папка workspace для конкретного чата (создаётся при первом обращении)."""
    path = os.path.join(WORKSPACE_ROOT, _chat_key(platform, chat_id))
    os.makedirs(path, exist_ok=True)
    return path


# ============================================================
# ИНДЕКС ФАЙЛОВ (чтобы брать их заново из Telegram)
# ============================================================
def _load_index(base: str) -> dict[str, Any]:
    path = os.path.join(base, INDEX_NAME)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("files"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"files": {}}


def _save_index(base: str, data: dict[str, Any]) -> None:
    path = os.path.join(base, INDEX_NAME)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError as exc:
        logger.debug(f"workspace index save: {exc}")


def register_file(platform: str, chat_id: int, rel: str, *,
                  file_id: str = "", message_id: int | None = None,
                  mime: str = "", url: str = "", kind: str = "upload") -> None:
    """Запоминает file_id/url файла, чтобы потом скачать его из чата."""
    base = workspace_dir(platform, chat_id)
    key = (rel or "").replace("\\", "/")
    data = _load_index(base)
    files = data.get("files")
    if not isinstance(files, dict):
        files = {}
        data["files"] = files
    entry = files.get(key) if isinstance(files.get(key), dict) else {}
    now = time.time()
    entry.update({
        "name": key,
        "kind": kind,
        "mime": mime or entry.get("mime", ""),
        "saved": entry.get("saved", now),
        "used": now,
        "removed": False,
    })
    if file_id:
        entry["file_id"] = file_id
    if message_id:
        entry["message_id"] = int(message_id)
    if url:
        entry["url"] = url
    files[key] = entry
    _save_index(base, data)


def mark_used(platform: str, chat_id: int, rel: str) -> None:
    base = workspace_dir(platform, chat_id)
    key = (rel or "").replace("\\", "/")
    data = _load_index(base)
    files = data.get("files")
    if not isinstance(files, dict):
        return
    entry = files.get(key)
    if isinstance(entry, dict):
        entry["used"] = time.time()
        _save_index(base, data)


def _entry_ttl(entry: dict[str, Any]) -> int:
    kind = str(entry.get("kind") or "")
    if kind in ("upload", "media") or entry.get("file_id") or entry.get("url"):
        return MEDIA_TTL_SECONDS if kind == "media" else UPLOAD_TTL_SECONDS
    return GENERATED_TTL_SECONDS


def cleanup_expired(platform: str, chat_id: int) -> int:
    """Удаляет файлы, которые давно не использовали. Индекс остаётся."""
    return _cleanup_dir(workspace_dir(platform, chat_id))


def cleanup_all() -> int:
    removed = 0
    try:
        for name in os.listdir(WORKSPACE_ROOT):
            path = os.path.join(WORKSPACE_ROOT, name)
            if os.path.isdir(path):
                removed += _cleanup_dir(path)
    except OSError:
        pass
    return removed


def _cleanup_dir(base: str) -> int:
    data = _load_index(base)
    files = data.get("files")
    if not isinstance(files, dict):
        return 0
    now = time.time()
    removed = 0
    for root, _dirs, names in os.walk(base):
        for name in names:
            if name == INDEX_NAME or name.startswith(INDEX_NAME):
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, base).replace("\\", "/")
            entry = files.get(rel) if isinstance(files.get(rel), dict) else {}
            try:
                used = float(entry.get("used") or os.path.getmtime(full))
            except (OSError, TypeError, ValueError):
                used = now
            if now - used <= _entry_ttl(entry):
                continue
            try:
                os.remove(full)
                removed += 1
                if entry:
                    entry["removed"] = True
                    entry["removed_at"] = now
            except OSError:
                continue
    # Старые записи индекса тоже не храним вечно.
    for key in list(files):
        entry = files.get(key)
        if not isinstance(entry, dict):
            del files[key]
            continue
        try:
            saved = float(entry.get("saved") or now)
        except (TypeError, ValueError):
            saved = now
        if now - saved > WORKSPACE_TTL_SECONDS:
            del files[key]
    _save_index(base, data)
    return removed


async def cleanup_loop(interval: int = 20) -> None:
    """Фоновая автоочистка: не держим картинки и файлы на сервере вечно."""
    while True:
        try:
            removed = cleanup_all()
            if removed:
                logger.info(f"🧹 workspace: удалено {removed} файлов")
        except Exception as exc:
            logger.debug(f"workspace cleanup: {exc}")
        await asyncio.sleep(interval)


async def recover_file(platform: str, chat_id: int, rel: str) -> bool:
    """Возвращает файл в workspace, заново скачав его из чата."""
    base = workspace_dir(platform, chat_id)
    key = (rel or "").replace("\\", "/")
    data = _load_index(base)
    files = data.get("files")
    entry = files.get(key) if isinstance(files, dict) and isinstance(files.get(key), dict) else None
    if not entry:
        return False
    raw: bytes | None = None
    try:
        if platform == "tg" and entry.get("file_id"):
            from src.telegram import tg_bot
            from src.util import get_tg_file_bytes
            raw = await get_tg_file_bytes(tg_bot, str(entry["file_id"]))
        elif entry.get("url"):
            from src.util import download_image_bytes
            raw = await download_image_bytes(str(entry["url"]))
    except Exception as exc:
        logger.warning(f"workspace recover {key}: {exc}")
    if not raw:
        return False
    full = safe_path(platform, chat_id, key)
    if full is None:
        return False
    try:
        os.makedirs(os.path.dirname(full) or base, exist_ok=True)
        with open(full, "wb") as f:
            f.write(raw)
        mark_used(platform, chat_id, key)
        return True
    except OSError as exc:
        logger.warning(f"workspace recover write {key}: {exc}")
        return False


def latest_archive(platform: str, chat_id: int) -> str | None:
    base = workspace_dir(platform, chat_id)
    best: tuple[float, str] | None = None
    for root, _dirs, names in os.walk(base):
        for name in names:
            if not name.lower().endswith(".zip"):
                continue
            full = os.path.join(root, name)
            try:
                mtime = os.path.getmtime(full)
            except OSError:
                continue
            if best is None or mtime > best[0]:
                best = (mtime, os.path.relpath(full, base).replace("\\", "/"))
    return best[1] if best else None


def latest_file(platform: str, chat_id: int) -> str | None:
    base = workspace_dir(platform, chat_id)
    best: tuple[float, str] | None = None
    for root, _dirs, names in os.walk(base):
        for name in names:
            if name == INDEX_NAME or name.startswith(INDEX_NAME):
                continue
            full = os.path.join(root, name)
            try:
                mtime = os.path.getmtime(full)
            except OSError:
                continue
            if best is None or mtime > best[0]:
                best = (mtime, os.path.relpath(full, base).replace("\\", "/"))
    return best[1] if best else None


def safe_path(platform: str, chat_id: int, rel: str | None) -> str | None:
    """Безопасно склеивает путь внутри workspace."""
    base = os.path.realpath(workspace_dir(platform, chat_id))
    raw = (rel or "").strip().strip('"').strip("'").replace("\\", "/")
    raw = raw.lstrip("/")
    if not raw:
        return base
    target = os.path.realpath(os.path.join(base, raw))
    if target != base and not target.startswith(base + os.sep):
        return None
    return target


def sanitize_name(name: str) -> str:
    base = os.path.basename((name or "file").replace("\\", "/"))
    base = re.sub(r'[<>:"|?*\x00-\x1f]', "_", base).strip(" .")
    return base[:120] or "file"


def unique_path(directory: str, name: str) -> str:
    """Не перезаписывает существующий файл — добавляет (1), (2) и т.д."""
    candidate = os.path.join(directory, name)
    if not os.path.exists(candidate):
        return candidate
    stem, ext = os.path.splitext(name)
    for i in range(1, 1000):
        candidate = os.path.join(directory, f"{stem} ({i}){ext}")
        if not os.path.exists(candidate):
            return candidate
    return os.path.join(directory, f"{stem} ({int(time.time())}){ext}")


def save_bytes(platform: str, chat_id: int, filename: str, data: bytes) -> str:
    """Сохраняет присланный файл/картинку в workspace. Возвращает относительный путь."""
    if not data:
        raise ValueError("пустой файл")
    base = workspace_dir(platform, chat_id)
    name = sanitize_name(filename)
    full = unique_path(base, name)
    with open(full, "wb") as f:
        f.write(data)
    return os.path.relpath(full, base)


def save_upload(platform: str, chat_id: int, filename: str, data: bytes,
                mime: str = "", *, file_id: str = "", message_id: int | None = None,
                url: str = "") -> str:
    """Как save_bytes, но подставляет расширение по mime и запоминает file_id."""
    name = sanitize_name(filename)
    if "." not in name:
        name += _EXT_BY_MIME.get((mime or "").lower(), ".bin")
    rel = save_bytes(platform, chat_id, name, data)
    kind = "media" if (mime or "").lower().startswith(("image/", "video/")) else "upload"
    register_file(platform, chat_id, rel, file_id=file_id, message_id=message_id,
                  mime=mime, url=url, kind=kind)
    return rel


def list_files(platform: str, chat_id: int) -> list[str]:
    base = workspace_dir(platform, chat_id)
    out: list[str] = []
    for root, _dirs, files in os.walk(base):
        for name in files:
            if name == INDEX_NAME or name.startswith(INDEX_NAME):
                continue
            out.append(os.path.relpath(os.path.join(root, name), base).replace("\\", "/"))
    out.sort()
    return out[:MAX_WORKSPACE_FILES]


def total_size(platform: str, chat_id: int) -> int:
    base = workspace_dir(platform, chat_id)
    total = 0
    for root, _dirs, files in os.walk(base):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                continue
    return total


def read_text(platform: str, chat_id: int, rel: str,
              start: int | None = None, end: int | None = None) -> str:
    """Читает файл или диапазон строк (1-based, включительно)."""
    full = safe_path(platform, chat_id, rel)
    if full is None or not os.path.isfile(full):
        raise FileNotFoundError(f"нет такого файла: {rel}")
    mark_used(platform, chat_id, rel)
    with open(full, "rb") as f:
        raw = f.read(2 * 1024 * 1024)
    if b"\x00" in raw[:1024]:
        raise ValueError("это бинарный файл, читать как текст нельзя")
    text = raw.decode("utf-8", errors="replace")
    if start or end:
        lines = text.splitlines()
        lo = max(1, start or 1)
        hi = min(len(lines), end or len(lines))
        text = "\n".join(lines[lo - 1:hi])
    if len(text) > MAX_READ_CHARS:
        text = text[:MAX_READ_CHARS] + "\n...[обрезано]"
    return text


def write_text(platform: str, chat_id: int, rel: str, content: str,
               append: bool = False) -> str:
    full = safe_path(platform, chat_id, rel)
    if full is None:
        raise ValueError("путь вне рабочей папки")
    if len(content) > 2 * 1024 * 1024:
        raise ValueError("файл слишком большой (максимум 2 МБ)")
    os.makedirs(os.path.dirname(full) or workspace_dir(platform, chat_id), exist_ok=True)
    mode = "a" if append else "w"
    with open(full, mode, encoding="utf-8", newline="\n") as f:
        f.write(content)
    saved = os.path.relpath(full, workspace_dir(platform, chat_id)).replace("\\", "/")
    register_file(platform, chat_id, saved, kind="generated")
    return saved


def replace_in_file(platform: str, chat_id: int, rel: str, old: str, new: str) -> int:
    full = safe_path(platform, chat_id, rel)
    if full is None or not os.path.isfile(full):
        raise FileNotFoundError(f"нет такого файла: {rel}")
    with open(full, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    count = text.count(old)
    if not count:
        return 0
    with open(full, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.replace(old, new))
    return count


def delete_path(platform: str, chat_id: int, rel: str) -> bool:
    full = safe_path(platform, chat_id, rel)
    if full is None or not os.path.exists(full) or full == workspace_dir(platform, chat_id):
        return False
    if os.path.isdir(full):
        shutil.rmtree(full, ignore_errors=True)
    else:
        os.remove(full)
    return True


def make_archive(platform: str, chat_id: int, rel: str = "",
                 archive_name: str = "kulsh_workspace.zip") -> str:
    """Пакует папку или файл workspace в zip. Возвращает относительный путь архива."""
    base = workspace_dir(platform, chat_id)
    target = safe_path(platform, chat_id, rel)
    if target is None or not os.path.exists(target):
        raise FileNotFoundError(f"нет такого пути: {rel or '.'}")
    out = unique_path(base, sanitize_name(archive_name))
    out_real = os.path.realpath(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.isdir(target):
            for root, _dirs, files in os.walk(target):
                for name in files:
                    if name == INDEX_NAME or name.startswith(INDEX_NAME):
                        continue
                    full = os.path.join(root, name)
                    if os.path.realpath(full) == out_real:
                        continue
                    zf.write(full, os.path.relpath(full, target))
        else:
            zf.write(target, os.path.basename(target))
    saved = os.path.relpath(out, base).replace("\\", "/")
    register_file(platform, chat_id, saved, kind="generated")
    return saved


def _safe_member_name(name: str) -> str:
    """Безопасный относительный путь внутри архива (без .. и абсолютных путей)."""
    parts: list[str] = []
    for part in (name or "").replace("\\", "/").split("/"):
        clean = sanitize_name(part)
        if not clean or clean in (".", ".."):
            continue
        parts.append(clean)
    return os.path.join(*parts) if parts else ""


def _safe_extract_zip(path: str, dest: str) -> list[str]:
    extracted: list[str] = []
    with zipfile.ZipFile(path) as zf:
        total = 0
        for info in zf.infolist():
            if info.is_dir():
                continue
            total += info.file_size
            if total > MAX_WORKSPACE_BYTES:
                raise ValueError("архив слишком большой")
            name = _safe_member_name(info.filename)
            if not name:
                continue
            target = os.path.join(dest, name)
            os.makedirs(os.path.dirname(target) or dest, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted.append(os.path.relpath(target, dest))
    return extracted


def _safe_extract_tar(path: str, dest: str) -> list[str]:
    extracted: list[str] = []
    with tarfile.open(path) as tf:
        total = 0
        for member in tf.getmembers():
            if not member.isfile():
                continue
            total += member.size
            if total > MAX_WORKSPACE_BYTES:
                raise ValueError("архив слишком большой")
            name = _safe_member_name(member.name)
            if not name:
                continue
            target = os.path.join(dest, name)
            os.makedirs(os.path.dirname(target) or dest, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                continue
            with open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted.append(os.path.relpath(target, dest))
    return extracted


def unpack_archive(platform: str, chat_id: int, rel: str) -> list[str]:
    """Распаковывает zip/tar в подпапку workspace. Возвращает список файлов."""
    full = safe_path(platform, chat_id, rel)
    if full is None or not os.path.isfile(full):
        raise FileNotFoundError(f"нет такого архива: {rel}")
    base = workspace_dir(platform, chat_id)
    stem = os.path.splitext(os.path.basename(full))[0]
    dest = unique_path(base, sanitize_name(stem) or "unpacked")
    os.makedirs(dest, exist_ok=True)
    lower = full.lower()
    if lower.endswith(".zip"):
        return _safe_extract_zip(full, dest)
    if lower.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")):
        return _safe_extract_tar(full, dest)
    # Прочие форматы, которые умеет stdlib (например .gztar/.xztar).
    try:
        import shutil as _sh
        _sh.unpack_archive(full, dest)
        return [
            os.path.relpath(os.path.join(root, name), dest)
            for root, _dirs, files in os.walk(dest)
            for name in files
        ][:MAX_WORKSPACE_FILES]
    except Exception as exc:
        raise ValueError(f"не смог распаковать архив: {exc}")


async def run_command(platform: str, chat_id: int, command: str) -> tuple[int, str]:
    """Безопасная терминальная команда внутри workspace."""
    from src.tools import run_safe_command
    base = workspace_dir(platform, chat_id)
    return await run_safe_command(base, command)


def cleanup_old() -> None:
    """Удаляет workspace, к которым не обращались дольше TTL."""
    now = time.time()
    try:
        for name in os.listdir(WORKSPACE_ROOT):
            path = os.path.join(WORKSPACE_ROOT, name)
            try:
                if os.path.isdir(path) and now - os.path.getmtime(path) > WORKSPACE_TTL_SECONDS:
                    shutil.rmtree(path, ignore_errors=True)
            except OSError:
                continue
    except OSError:
        pass


def describe(platform: str, chat_id: int) -> str:
    base = workspace_dir(platform, chat_id)
    files = list_files(platform, chat_id)
    data = _load_index(base)
    known = data.get("files") if isinstance(data.get("files"), dict) else {}
    missing = [
        name for name, entry in (known or {}).items()
        if isinstance(entry, dict) and name not in files
        and (entry.get("file_id") or entry.get("url"))
    ]
    if not files and not missing:
        return "рабочая папка пуста"
    lines: list[str] = []
    shown = files[:40]
    if shown:
        lines.append("на сервере: " + ", ".join(shown))
        if len(files) > 40:
            lines.append(f"... (+{len(files) - 40})")
    if missing:
        lines.append("в чате (верну через !recall_file): " + ", ".join(missing[:20]))
    return "\n".join(lines)


def as_bytes(platform: str, chat_id: int, rel: str) -> bytes:
    full = safe_path(platform, chat_id, rel)
    if full is None or not os.path.isfile(full):
        raise FileNotFoundError(f"нет такого файла: {rel}")
    mark_used(platform, chat_id, rel)
    with open(full, "rb") as f:
        return f.read()


def file_info(platform: str, chat_id: int, rel: str) -> dict[str, Any]:
    full = safe_path(platform, chat_id, rel)
    if full is None or not os.path.exists(full):
        raise FileNotFoundError(f"нет такого файла: {rel}")
    stat = os.stat(full)
    return {
        "path": rel,
        "name": os.path.basename(full),
        "size": stat.st_size,
        "is_dir": os.path.isdir(full),
        "modified": stat.st_mtime,
    }


# ============================================================
# FILE ACTIONS FROM MODEL MARKERS
# ============================================================
_READ_RE = re.compile(r'!\s*(?:read|cat)[ \t]+([^\n]+?)[ \t]*$', re.IGNORECASE | re.MULTILINE)
_WRITE_RE = re.compile(
    r'!\s*(write|append)\s+([^\n`]+?)\s*```[a-zA-Z0-9]*[ \t]*\n([\s\S]*?)```',
    re.IGNORECASE,
)
_REPLACE_RE = re.compile(
    r'!\s*replace[ \t]+([^\n:]+?)[ \t]*::[ \t]*([\s\S]*?)[ \t]*::[ \t]*([^\n]*)',
    re.IGNORECASE,
)
_SEND_RE = re.compile(r'!\s*send(?:file)?(?:[ \t]+([^\n]+?))?[ \t]*$', re.IGNORECASE | re.MULTILINE)
_RECALL_FILE_RE = re.compile(r'!\s*recall[\s_]*file[ \t]+([^\n]+?)[ \t]*$', re.IGNORECASE | re.MULTILINE)
_UNPACK_RE = re.compile(r'!\s*unpack[ \t]+([^\n]+?)[ \t]*$', re.IGNORECASE | re.MULTILINE)
_PACK_RE = re.compile(r'!\s*pack(?:[ \t]+([^\n]+?))?[ \t]*$', re.IGNORECASE | re.MULTILINE)
_RUN_RE = re.compile(r'!\s*run[ \t]+([^\n]+?)[ \t]*$', re.IGNORECASE | re.MULTILINE)
_FILES_RE = re.compile(r'!\s*(?:files|ls|workspace)\b', re.IGNORECASE)
_SAVE_RE = re.compile(r'!\s*save[ \t]+([^\n]+?)[ \t]*$', re.IGNORECASE | re.MULTILINE)


class WorkspaceAction:
    __slots__ = ("kind", "payload", "status")

    def __init__(self, kind: str, payload: str = "", status: str = "") -> None:
        self.kind = kind
        self.payload = payload
        self.status = status


def extract_actions(text: str) -> tuple[str, list[WorkspaceAction]]:
    """Вырезает файловые маркеры из ответа модели.

    Возвращает (очищенный текст, список действий). Сами действия выполняет
    `execute_action`, потому что отправка файлов зависит от платформы.
    """
    if not text:
        return "", []
    actions: list[WorkspaceAction] = []
    out = text

    for match in list(_WRITE_RE.finditer(out)):
        actions.append(WorkspaceAction(match.group(1).lower(), f"{match.group(2).strip()}\x1f{match.group(3)}"))
    out = _WRITE_RE.sub("", out)

    # Если модель написала !write путь без ```-блока — берём всё до следующего
    # маркера. Иначе .py/.json/.md терялись и уходили обычным сообщением.
    lines = out.splitlines()
    kept: list[str] = []
    i = 0
    while i < len(lines):
        bare = re.match(r'^\s*!\s*(write|append)\s+(\S+)\s*$', lines[i], re.IGNORECASE)
        if not bare:
            kept.append(lines[i])
            i += 1
            continue
        j = i + 1
        body: list[str] = []
        while j < len(lines) and not re.match(r'^\s*!\s*[A-Za-z_]', lines[j]):
            body.append(lines[j])
            j += 1
        # Если блок кода не поймался основным regex — снимаем ```-обёртку,
        # чтобы в файл не попали сами backticks.
        if body and body[0].strip().startswith("```"):
            body = body[1:]
            if body and body[-1].strip().startswith("```"):
                body = body[:-1]
        content = "\n".join(body).strip("\n")
        if content.strip():
            actions.append(WorkspaceAction(
                bare.group(1).lower(), f"{bare.group(2).strip()}\x1f{content}"
            ))
            i = j
            continue
        kept.append(lines[i])
        i += 1
    out = "\n".join(kept)

    for match in list(_REPLACE_RE.finditer(out)):
        actions.append(WorkspaceAction(
            "replace",
            f"{match.group(1).strip()}\x1f{match.group(2).strip()}\x1f{match.group(3)}",
        ))
    out = _REPLACE_RE.sub("", out)

    for match in list(_RUN_RE.finditer(out)):
        actions.append(WorkspaceAction("run", match.group(1).strip()))
    out = _RUN_RE.sub("", out)

    for match in list(_UNPACK_RE.finditer(out)):
        actions.append(WorkspaceAction("unpack", match.group(1).strip()))
    out = _UNPACK_RE.sub("", out)

    for match in list(_PACK_RE.finditer(out)):
        actions.append(WorkspaceAction("pack", (match.group(1) or "").strip()))
    out = _PACK_RE.sub("", out)

    for match in list(_SEND_RE.finditer(out)):
        actions.append(WorkspaceAction("send", (match.group(1) or "").strip()))
    out = _SEND_RE.sub("", out)

    for match in list(_RECALL_FILE_RE.finditer(out)):
        actions.append(WorkspaceAction("recall", match.group(1).strip()))
    out = _RECALL_FILE_RE.sub("", out)

    for match in list(_SAVE_RE.finditer(out)):
        actions.append(WorkspaceAction("save", match.group(1).strip()))
    out = _SAVE_RE.sub("", out)

    for match in list(_READ_RE.finditer(out)):
        actions.append(WorkspaceAction("read", match.group(1).strip()))
    out = _READ_RE.sub("", out)

    if _FILES_RE.search(out):
        actions.append(WorkspaceAction("list"))
        out = _FILES_RE.sub("", out)

    return re.sub(r'\n{3,}', '\n\n', out).strip(), actions


async def execute_action(platform: str, chat_id: int, action: WorkspaceAction) -> str:
    """Выполняет действие и возвращает человекочитаемый результат."""
    try:
        if action.kind == "list":
            return describe(platform, chat_id)
        if action.kind == "read":
            raw = action.payload
            rel, _, rng = raw.partition(" ")
            start = end = None
            if rng:
                m = re.match(r'(\d+)\s*[-:]\s*(\d+)', rng.strip())
                if m:
                    start, end = int(m.group(1)), int(m.group(2))
                elif rng.strip().isdigit():
                    start = int(rng.strip())
            try:
                text = read_text(platform, chat_id, rel, start, end)
            except FileNotFoundError:
                if not await recover_file(platform, chat_id, rel):
                    raise
                text = read_text(platform, chat_id, rel, start, end)
            return f"=== {rel} ===\n{text}"
        if action.kind in ("write", "append"):
            rel, _, content = action.payload.partition("\x1f")
            saved = write_text(platform, chat_id, rel, content, append=action.kind == "append")
            return f"записал {saved} ({len(content)} символов)"
        if action.kind == "replace":
            parts = action.payload.split("\x1f")
            if len(parts) < 3:
                return "не понял, что заменить"
            rel, old, new = parts[0], parts[1], parts[2]
            count = replace_in_file(platform, chat_id, rel, old, new)
            return f"заменил {count} вхождений в {rel}" if count else f"не нашёл такой текст в {rel}"
        if action.kind == "run":
            code, out = await run_command(platform, chat_id, action.payload)
            return f"$ {action.payload}\n{out}".strip()[:4000] if code == 0 else f"ошибка {code}: {out}"[:2000]
        if action.kind == "unpack":
            files = unpack_archive(platform, chat_id, action.payload)
            return f"распаковал {len(files)} файлов: " + ", ".join(files[:30])
        if action.kind == "pack":
            path = make_archive(platform, chat_id, action.payload)
            return f"собрал архив {path}"
        if action.kind == "recall":
            rel = action.payload.strip()
            if os.path.isfile(safe_path(platform, chat_id, rel) or ""):
                mark_used(platform, chat_id, rel)
                return f"файл {rel} на месте"
            if await recover_file(platform, chat_id, rel):
                return f"вернул {rel} из чата"
            return f"не смог вернуть {rel}: в чате нет копии"
        if action.kind == "save":
            return f"файл {action.payload} в рабочей папке"
    except Exception as exc:
        return f"не получилось: {exc}"
    return ""

