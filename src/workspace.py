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
MAX_READ_CHARS = 12000
WORKSPACE_TTL_SECONDS = 7 * 24 * 3600

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
                mime: str = "") -> str:
    """Как save_bytes, но подставляет расширение по mime, если его нет."""
    name = sanitize_name(filename)
    if "." not in name:
        name += _EXT_BY_MIME.get((mime or "").lower(), ".bin")
    return save_bytes(platform, chat_id, name, data)


def list_files(platform: str, chat_id: int) -> list[str]:
    base = workspace_dir(platform, chat_id)
    out: list[str] = []
    for root, _dirs, files in os.walk(base):
        for name in files:
            out.append(os.path.relpath(os.path.join(root, name), base))
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
    os.makedirs(os.path.dirname(full) or workspace_dir(platform, chat_id), exist_ok=True)
    mode = "a" if append else "w"
    with open(full, mode, encoding="utf-8", newline="\n") as f:
        f.write(content)
    return os.path.relpath(full, workspace_dir(platform, chat_id))


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
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.isdir(target):
            for root, _dirs, files in os.walk(target):
                for name in files:
                    full = os.path.join(root, name)
                    zf.write(full, os.path.relpath(full, target))
        else:
            zf.write(target, os.path.basename(target))
    return os.path.relpath(out, base)


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
            name = sanitize_name(info.filename)
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
            name = sanitize_name(member.name)
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
    if lower.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2")):
        return _safe_extract_tar(full, dest)
    raise ValueError("поддерживаются zip и tar-архивы")


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
    files = list_files(platform, chat_id)
    if not files:
        return "рабочая папка пуста"
    shown = ", ".join(files[:40])
    if len(files) > 40:
        shown += f" ... (+{len(files) - 40})"
    return shown


def as_bytes(platform: str, chat_id: int, rel: str) -> bytes:
    full = safe_path(platform, chat_id, rel)
    if full is None or not os.path.isfile(full):
        raise FileNotFoundError(f"нет такого файла: {rel}")
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
_READ_RE = re.compile(r'!\s*(?:read|cat)\s+([^\n]+?)\s*$', re.IGNORECASE | re.MULTILINE)
_WRITE_RE = re.compile(
    r'!\s*(write|append)\s+([^\n]+?)\s*\n```[a-zA-Z0-9]*\s*\n([\s\S]*?)```',
    re.IGNORECASE,
)
_REPLACE_RE = re.compile(
    r'!\s*replace\s+([^\n:]+?)\s*::\s*([\s\S]*?)\s*::\s*([^\n]*)',
    re.IGNORECASE,
)
_SEND_RE = re.compile(r'!\s*send(?:file)?\s+([^\n]+?)\s*$', re.IGNORECASE | re.MULTILINE)
_UNPACK_RE = re.compile(r'!\s*unpack\s+([^\n]+?)\s*$', re.IGNORECASE | re.MULTILINE)
_PACK_RE = re.compile(r'!\s*pack(?:\s+([^\n]+?))?\s*$', re.IGNORECASE | re.MULTILINE)
_RUN_RE = re.compile(r'!\s*run\s+([^\n]+?)\s*$', re.IGNORECASE | re.MULTILINE)
_FILES_RE = re.compile(r'!\s*(?:files|ls|workspace)\b', re.IGNORECASE)
_SAVE_RE = re.compile(r'!\s*save\s+([^\n]+?)\s*$', re.IGNORECASE | re.MULTILINE)


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
        actions.append(WorkspaceAction("send", match.group(1).strip()))
    out = _SEND_RE.sub("", out)

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
        if action.kind == "save":
            return f"файл {action.payload} в рабочей папке"
    except Exception as exc:
        return f"не получилось: {exc}"
    return ""

