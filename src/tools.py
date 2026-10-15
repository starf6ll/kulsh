# Kulsh GPT | v2.39.0
# by (main author): starfall-apk
# coauthor & bot hosting: pomidorka1515

"""Archive unpack/edit/repack tools used from Telegram DMs."""

import asyncio
import json
import os
import shutil
import tempfile
import zipfile
from typing import Any, cast

from telebot import types as types
from telebot.types import InputFile

from src.ai import ask_ai_async
from src.util import (
    MAX_FILE_SIZE,
    MAX_FILES,
    MAX_TOTAL_UNPACKED,
    SAFE_COMMANDS,
    tr,
    clean_json_text,
    get_user_config,
    logger,
    JsonDict,

    tools_sessions,)


def _bot() -> Any:
    from src import telegram as tg
    return tg.tg_bot


async def reply_tg_html(message: types.Message, text: str) -> None:
    from src import telegram as tg
    await tg.reply_tg_html(message, text)


async def send_tg_ai_response(
    message: types.Message,
    chat_id: int,
    user_id: int,
    answer: str,
) -> None:
    from src import telegram as tg
    await tg.send_tg_ai_response(message, chat_id, user_id, answer)


def safe_join(base: str, rel: str) -> str | None:
    if not rel:
        return base
    target = os.path.realpath(os.path.join(base, rel))
    base_real = os.path.realpath(base)
    if not target.startswith(base_real + os.sep) and target != base_real:
        return None
    return target


def list_files(base: str) -> list[str]:
    out: list[str] = []
    for root, _dirs, files in os.walk(base):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, base)
            out.append(rel)
    return out


def is_text_file(path: str) -> bool:
    try:
        with open(path, 'rb') as f:
            chunk = f.read(1024)
        if b'\x00' in chunk:
            return False
        chunk.decode('utf-8', errors='strict')
        return True
    except Exception:
        return False


async def extract_archive(zip_path: str, dest_dir: str) -> list[str]:
    def _do() -> list[str]:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            total = 0
            count = 0
            for info in zf.infolist():
                if info.is_dir():
                    continue
                count += 1
                if count > MAX_FILES:
                    raise Exception("Слишком много файлов в архиве")
                total += info.file_size
                if total > MAX_TOTAL_UNPACKED:
                    raise Exception("Распакованный архив слишком большой")
                target = safe_join(dest_dir, info.filename)
                if target is None:
                    raise Exception(f"Небезопасный путь: {info.filename}")
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(info) as src, open(target, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
        return list_files(dest_dir)
    return await asyncio.to_thread(_do)


async def create_archive(source_dir: str, out_zip: str) -> None:
    def _do() -> None:
        with zipfile.ZipFile(out_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(source_dir):
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, source_dir)
                    zf.write(full, rel)
    await asyncio.to_thread(_do)


async def run_safe_command(base_dir: str, cmd: str) -> tuple[int, str]:
    parts = cmd.strip().split()
    if not parts:
        return 1, "пустая команда"
    prog = parts[0].lower()
    if prog not in SAFE_COMMANDS:
        return 1, f"команда '{prog}' не разрешена"
    for p in parts:
        if any(ch in p for ch in (';', '&', '|', '`', '$', '<', '>', '\n')):
            return 1, "метасимволы запрещены"
    try:
        proc = await asyncio.create_subprocess_exec(
            *parts, cwd=base_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        out = (stdout or b'').decode('utf-8', errors='replace')[:8000]
        err = (stderr or b'').decode('utf-8', errors='replace')[:2000]
        if err:
            out += "\n[stderr]\n" + err
        return proc.returncode or 0, out
    except asyncio.TimeoutError:
        return 1, "команда не завершилась за 15 сек"
    except Exception as e:
        return 1, f"ошибка: {e}"


async def tool_edit_archive(message: types.Message, user_request: str,
                            archive_bytes: bytes, filename: str) -> None:
    if message.from_user is None:
        return
    user_id = message.from_user.id
    chat_id = message.chat.id
    cfg = get_user_config("tg", chat_id, user_id)
    lang = cfg.get("language", "ru")
    status = await _bot().send_message(chat_id, tr(lang, "tool_unpacking"))
    work_dir = tempfile.mkdtemp(prefix="kulsh_tools_")
    tools_sessions[chat_id] = {"dir": work_dir, "user_id": user_id}
    try:
        arch_path = os.path.join(work_dir, "input.zip")
        with open(arch_path, 'wb') as f:
            f.write(archive_bytes)
        files = await extract_archive(arch_path, work_dir)
        files_display = ", ".join(files[:30])
        if len(files) > 30:
            files_display += f" ... (+{len(files) - 30})"
        await _bot().edit_message_text(tr(lang, "tool_unpacked", files_display),
                                       chat_id, status.message_id)

        contents: dict[str, str] = {}
        for rel in files[:50]:
            full = safe_join(work_dir, rel)
            if full and os.path.exists(full) and os.path.getsize(full) < MAX_FILE_SIZE:
                if is_text_file(full):
                    try:
                        with open(full, 'r', encoding='utf-8', errors='replace') as f:
                            contents[rel] = f.read()
                    except Exception:
                        pass
        files_context = "\n\n".join(f"=== {fn} ===\n{c[:6000]}" for fn, c in contents.items())
        if len(files_context) > 60000:
            files_context = files_context[:60000] + "\n...[обрезано]"

        await _bot().edit_message_text(tr(lang, "tool_analyzing", len(contents)),
                                       chat_id, status.message_id)

        prompt = (
            f"Пользователь отправил архив '{filename}' и попросил:\n\n{user_request}\n\n"
            f"Содержимое:\n{files_context}\n\n"
            "Верни JSON-объект строго:\n"
            '{"summary": "краткое описание (на русском, дружелюбно, в стиле Кульша)", '
            '"files": {"путь": "полное новое содержимое файла", ...}}\n\n'
            "Включай в 'files' только изменённые/новые файлы. Только JSON, без markdown."
        )
        raw = await ask_ai_async(
            prompt=prompt,
            system_instruction_override=(
                "Ты инструмент редактирования кода. Отвечай ТОЛЬКО валидным JSON с полями 'summary' и 'files'. "
                "Никаких пояснений, markdown или текста."
            ),
            chat_id=chat_id, user_id=user_id, platform="tg",
        )
        try:
            data = json.loads(clean_json_text(raw))
        except Exception as e:
            await _bot().edit_message_text(tr(lang, "tool_parse_fail", str(e)),
                                           chat_id, status.message_id)
            return

        summary = data.get("summary", "готово")
        new_files = data.get("files", {})
        if not isinstance(new_files, dict) or not new_files:
            await _bot().edit_message_text(tr(lang, "tool_no_changes", summary),
                                           chat_id, status.message_id)
            return
        new_files = cast(JsonDict, new_files)

        await _bot().edit_message_text(tr(lang, "tool_editing", len(new_files)),
                                       chat_id, status.message_id)
        for rel, new_content in new_files.items():
            full = safe_join(work_dir, rel)
            if full is None:
                continue
            os.makedirs(os.path.dirname(full) or work_dir, exist_ok=True)
            with open(full, 'w', encoding='utf-8') as f:
                f.write(new_content)

        await _bot().edit_message_text(tr(lang, "tool_repacking"),
                                       chat_id, status.message_id)
        out_zip = os.path.join(work_dir, f"edited_{filename or 'archive.zip'}")
        await create_archive(work_dir, out_zip)

        await _bot().edit_message_text(tr(lang, "tool_sending"),
                                       chat_id, status.message_id)
        with open(out_zip, 'rb') as f:
            await _bot().send_document(
                chat_id, InputFile(f, file_name=os.path.basename(out_zip)),
                caption=f"🍷🗿 {summary}",
            )
        await _bot().edit_message_text(tr(lang, "tool_done"), chat_id, status.message_id)
    except Exception as e:
        logger.error(f"tool_edit_archive: {e}")
        try:
            await _bot().edit_message_text(tr(lang, "tool_error", str(e)), chat_id, status.message_id)
        except Exception:
            pass
    finally:
        try:
            if work_dir and os.path.exists(work_dir):
                shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass
        tools_sessions.pop(chat_id, None)


async def tool_review_file(message: types.Message, user_request: str,
                           file_bytes: bytes, filename: str) -> None:
    if message.from_user is None:
        return
    user_id = message.from_user.id
    chat_id = message.chat.id
    cfg = get_user_config("tg", chat_id, user_id)
    _lang = cfg.get("language", "ru")
    try:
        text = file_bytes.decode('utf-8', errors='replace')
    except Exception:
        await reply_tg_html(message, "не могу прочитать файл как текст")
        return
    if len(text) > MAX_FILE_SIZE:
        text = text[:MAX_FILE_SIZE] + "\n...[обрезано]"
    prompt = (
        f"Пользователь отправил файл '{filename}' и просит:\n\n{user_request}\n\n"
        f"Содержимое файла:\n```\n{text}\n```\n\n"
        "Ответь в стиле Кульша: коротко разбери, ответь на вопрос. Не редактируй файл."
    )
    answer = await ask_ai_async(prompt=prompt, chat_id=chat_id, user_id=user_id, platform="tg")
    await send_tg_ai_response(message, chat_id, user_id, answer)

