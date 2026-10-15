# Kulsh GPT | v2.45.0
# by (main author): starfall-apk
# coauthor & bot hosting: pomidorka1515

"""Looksmaxxing + Femboy infographics and their AI prompts."""

import json
import os
from io import BytesIO
from typing import Any, cast

from PIL import Image, ImageDraw, ImageFont

from src.ai import ask_ai_async
from src.util import (
    FEMBOY_TIER_DISTRIBUTION,
    FEMBOY_TIER_RULES_STRICT,
    Font,
    JsonDict,
    TIER_DISTRIBUTION,
    TIER_RULES_F,
    TIER_RULES_M,
    TIER_RULES_STRICT,
    json_dict,
    tr,
    clean_json_text,
    find_femboy_tier_key,
    find_tier_key,
    get_femboy_tier_color,
    get_tier_color,
    logger,
)

# ============================================================
# FONTS / WRAP
# ============================================================
def load_font(size: int) -> Font:
    font_path = os.path.join("fonts", "Montserrat-Bold.ttf")
    try:
        return ImageFont.truetype(font_path, size)
    except IOError:
        return ImageFont.load_default()


def add_bullet(text: str) -> str:
    if text.startswith("•") or text.startswith("-"):
        return text
    return f"• {text}"


def wrap_text(text: str, draw: ImageDraw.ImageDraw, font: Font, max_width: int) -> list[str]:
    words = text.split(' ')
    lines: list[str] = []
    cur = ""
    for w in words:
        test = f"{cur} {w}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def block_height(lines: list[str], font: Font, line_spacing: int, draw: ImageDraw.ImageDraw) -> int:
    total = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        total += int(bbox[3] - bbox[1]) + line_spacing
    if total > 0:
        total -= line_spacing
    return total


# ============================================================
# PSL INFOGRAPHIC
# ============================================================
async def create_infographic(photo_bytes: bytes, data: JsonDict, theme: str = "dark", lang: str = "en") -> BytesIO:
    if lang == "ru":
        title_text = "ОТЧЁТ LOOKSMAXXING"
        psl_label = "PSL"
        strengths_label = "ПРЕИМУЩЕСТВ."
        weaknesses_label = "НЕДОСТАТКИ"
        full_analysis_text = "Полный анализ в сообщении"
        metric_names = {"skin": "Кожа", "eyes": "Глаза", "jawline": "Челюсть", "bloat": "Одутловатость",
                        "hair": "Волосы", "bone_structure": "Костная структура", "symmetry": "Симметрия",
                        "canthal_tilt": "Кант. наклон"}
        better_than_fmt = "Вы превосходите {}% людей"
        distribution_caption = "Распределение тиров"
        potential_label = "Потенциал:"
    else:
        title_text = "LOOKSMAXXING REPORT"
        psl_label = "PSL"
        strengths_label = "STRENGTHS"
        weaknesses_label = "WEAKNESSES"
        full_analysis_text = "Full analysis in the message"
        metric_names = {"skin": "Skin", "eyes": "Eyes", "jawline": "Jawline", "bloat": "Bloat",
                        "hair": "Hair", "bone_structure": "Bone structure", "symmetry": "Symmetry",
                        "canthal_tilt": "Canthal tilt"}
        better_than_fmt = "You outperform {}% of people"
        distribution_caption = "Tier distribution"
        potential_label = "Potential:"

    if theme == "light":
        bg_color = "#F9F9FB"
        text_primary = "#1A1A2E"
        text_secondary = "#4A4A6A"
        text_tertiary = "#6B6B80"
        accent = "#2B6CB0"
        line_color = "#D1D5DB"
        scale_bg = "#E5E7EB"
        weak_color = "#C53030"
        highlight_outline = "#1A1A2E"
    else:
        bg_color = "#0E0E12"
        text_primary = "#F3F4F6"
        text_secondary = "#9CA3AF"
        text_tertiary = "#6B6B80"
        accent = "#10B981"
        line_color = "#2A2A3A"
        scale_bg = "#2A2A3A"
        weak_color = "#E53E3E"
        highlight_outline = "#FFFFFF"

    canvas_w, canvas_h = 1000, 1000
    image = Image.new("RGBA", (canvas_w, canvas_h), bg_color)
    draw = ImageDraw.Draw(image)

    font_title = load_font(34)
    font_psl_num = load_font(56)
    font_sub = load_font(24)
    font_text = load_font(18)
    font_small = load_font(15)
    font_scale = load_font(16)
    list_font = load_font(17)
    font_tier_label = load_font(13)

    draw.text((40, 25), title_text, fill=text_tertiary, font=font_title)
    draw.line([(40, 70), (canvas_w - 40, 70)], fill=line_color, width=1)

    user_img = Image.open(BytesIO(photo_bytes)).convert("RGBA")
    user_img.thumbnail((430, 530), Image.Resampling.LANCZOS)
    mask = Image.new("L", user_img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0) + user_img.size, radius=28, fill=255)
    rounded = Image.new("RGBA", user_img.size, (0, 0, 0, 0))
    rounded.paste(user_img, (0, 0), mask=mask)
    photo_x, photo_y = 40, 100
    image.paste(rounded, (photo_x, photo_y), rounded)

    psl_score = data.get("psl", "N/A")
    tier_name = str(data.get("tier", "N/A")).upper()
    gender = data.get("gender", "N/A")
    potential = data.get("potential", "N/A")
    try:
        psl_val = max(1.0, min(8.0, float(psl_score)))
    except (ValueError, TypeError):
        psl_val = 1.0
    current_tier_idx = -1
    fk = find_tier_key(tier_name)
    if fk:
        for idx, t in enumerate(TIER_DISTRIBUTION):
            if t["key"] == fk:
                current_tier_idx = idx
                break
    if current_tier_idx == -1:
        for idx, t in enumerate(TIER_DISTRIBUTION):
            if float(t["psl_low"]) <= psl_val <= float(t["psl_high"]):
                current_tier_idx = idx
                break
    if current_tier_idx == -1:
        current_tier_idx = 4

    better_than = max(0.1, min(99.9, (psl_val - 1) / 7 * 100))
    better_text = better_than_fmt.format(round(better_than, 1))
    photo_bottom = photo_y + rounded.size[1]
    draw.text((40, photo_bottom + 20), better_text, fill=text_secondary, font=font_sub)

    chart_x = 40
    chart_y = photo_bottom + 65
    chart_width = 430
    chart_height = 20
    total_range = 8.0 - 1.0
    for tier in TIER_DISTRIBUTION:
        low = float(tier["psl_low"])
        high = float(tier["psl_high"])
        tier_key = str(tier["key"])
        tier_short = str(tier["short"])
        x_start = chart_x + (low - 1.0) / total_range * chart_width
        x_end = chart_x + (high - 1.0) / total_range * chart_width
        draw.rectangle((x_start, chart_y, x_end, chart_y + chart_height), fill=get_tier_color(tier_key))
        if tier_key == str(TIER_DISTRIBUTION[current_tier_idx]["key"]):
            draw.rectangle([x_start - 1, chart_y - 1, x_end + 1, chart_y + chart_height + 1],
                           outline=highlight_outline, width=2)
        tb = draw.textbbox((0, 0), tier_short, font=font_tier_label)
        tw = tb[2] - tb[0]
        draw.text(((x_start + x_end) / 2 - tw / 2, chart_y + chart_height + 4),
                  tier_short, fill=text_secondary, font=font_tier_label)
    draw.text((40, chart_y + chart_height + 30), distribution_caption, fill=text_tertiary, font=font_small)

    start_x = 510
    right_top_y = 100
    draw.text((start_x, right_top_y), psl_label, fill=text_tertiary, font=font_sub)
    draw.text((start_x, right_top_y + 35), f"{psl_score}", fill=text_primary, font=font_psl_num)
    draw.text((start_x, right_top_y + 110), f"{tier_name} · {gender}", fill=accent, font=font_sub)
    draw.text((start_x, right_top_y + 145), f"{potential_label} {potential}", fill=text_secondary, font=font_small)

    psl_bar_x, psl_bar_y = start_x, right_top_y + 200
    psl_bar_w, psl_bar_h = 400, 20
    draw.rounded_rectangle((psl_bar_x, psl_bar_y, psl_bar_x + psl_bar_w, psl_bar_y + psl_bar_h),
                           radius=10, fill=scale_bg)
    fw = int((psl_val - 1) / 7 * psl_bar_w)
    if fw > 0:
        draw.rounded_rectangle((psl_bar_x, psl_bar_y, psl_bar_x + fw, psl_bar_y + psl_bar_h),
                               radius=10, fill=get_tier_color(tier_name))
    for i in range(1, 9):
        x = psl_bar_x + (i - 1) / 7 * psl_bar_w
        draw.line([(x, psl_bar_y - 6), (x, psl_bar_y)], fill=text_tertiary, width=1)
        bbox = draw.textbbox((0, 0), str(i), font=font_scale)
        tw = bbox[2] - bbox[0]
        draw.text((x - tw / 2, psl_bar_y - 24), str(i), fill=text_secondary, font=font_scale)

    metrics_mapping = [
        ("skin", data.get("skin", "N/A")), ("eyes", data.get("eyes", "N/A")),
        ("jawline", data.get("jawline", "N/A")), ("bloat", data.get("bloat", "N/A")),
        ("hair", data.get("hair", "N/A")), ("bone_structure", data.get("bone_structure", "N/A")),
        ("symmetry", data.get("symmetry", "N/A")), ("canthal_tilt", data.get("canthal_tilt", "N/A")),
    ]
    right_margin = start_x + 430
    col1_x = start_x
    col1_width = 200
    col2_x = col1_x + col1_width + 20
    col2_width = right_margin - col2_x
    base_row_height = 38
    min_padding = 6
    line_spacing = 2
    current_y = float(psl_bar_y + psl_bar_h + 25)
    for key, val_str in metrics_mapping:
        title = metric_names.get(key, key)
        tb = draw.textbbox((0, 0), title, font=font_text)
        title_h = tb[3] - tb[1]
        val_lines = wrap_text(str(val_str), draw, font_text, col2_width)
        val_block_h = block_height(val_lines, font_text, line_spacing, draw)
        row_height = max(base_row_height, title_h + 2 * min_padding, val_block_h + 2 * min_padding)
        draw.line([(col1_x, current_y), (right_margin, current_y)], fill=line_color, width=1)
        draw.text((col1_x, current_y + (row_height - title_h) / 2), title, fill=text_secondary, font=font_text)
        val_y = float(current_y) + (row_height - val_block_h) / 2
        for line in val_lines:
            bbox = draw.textbbox((0, 0), line, font=font_text)
            lh = bbox[3] - bbox[1]
            draw.text((col2_x, val_y), line, fill=text_primary, font=font_text)
            val_y += float(lh) + line_spacing
        current_y += float(row_height)
    draw.line([(col1_x, current_y), (right_margin, current_y)], fill=line_color, width=1)

    raw_pros = data.get("pros", [])
    raw_cons = data.get("cons", [])
    if isinstance(raw_pros, str):
        raw_pros = [raw_pros]
    if isinstance(raw_cons, str):
        raw_cons = [raw_cons]
    pros: list[str] = []
    cons: list[str] = []
    if isinstance(raw_pros, list):
        pros = [add_bullet(str(p)) for p in cast(list[object], raw_pros)]
    if isinstance(raw_cons, list):
        cons = [add_bullet(str(c)) for c in cast(list[object], raw_cons)]
    col_y = current_y + 20
    draw.text((start_x, col_y), strengths_label, fill=accent, font=font_sub)
    draw.text((start_x + 220, col_y), weaknesses_label, fill=weak_color, font=font_sub)
    col_width = 200
    line_height = 26
    list_start_y = col_y + 38

    def render_list(items: list[str], x: int, y: int, color: str, max_width: int = col_width) -> int:
        cy = y
        for item in items:
            for line in wrap_text(item, draw, list_font, max_width):
                draw.text((x, cy), line, fill=color, font=list_font)
                cy += line_height
            cy += 4
        return cy

    end_left = render_list(pros, start_x + 10, int(list_start_y), text_primary)
    end_right = render_list(cons, start_x + 230, int(list_start_y), text_primary)
    max_y = max(end_left, end_right)
    draw.text((40, max_y + 30), full_analysis_text, fill=text_tertiary, font=font_small)
    out = BytesIO()
    image.save(out, format="PNG")
    out.seek(0)
    return out


# ============================================================
# PSL BATTLE INFOGRAPHIC
# ============================================================
async def create_battle_infographic(
    p1: bytes, p2: bytes, data: JsonDict, theme: str = "dark", lang: str = "en",
) -> BytesIO:
    if lang == "ru":
        title = "БАТТЛ LOOKSMAXXING"
        factor_labels = {"skin": "Кожа", "eyes": "Глаза", "jawline": "Челюсть", "bloat": "Одутловатость",
                         "hair": "Волосы", "bone_structure": "Костная структура", "symmetry": "Симметрия",
                         "canthal_tilt": "Кант. наклон"}
        mogged_text = "МОГГНУТ"
        winner_label = "ПОБЕДИТЕЛЬ"
    else:
        title = "LOOKSMAXXING BATTLE"
        factor_labels = {"skin": "Skin", "eyes": "Eyes", "jawline": "Jawline", "bloat": "Bloat",
                         "hair": "Hair", "bone_structure": "Bone structure", "symmetry": "Symmetry",
                         "canthal_tilt": "Canthal tilt"}
        mogged_text = "MOGGED"
        winner_label = "WINNER"

    if theme == "light":
        bg_color = "#F9F9FB"
        text_primary = "#1A1A2E"
        text_secondary = "#4A4A6A"
        text_tertiary = "#6B6B80"
        accent = "#2B6CB0"
        line_color = "#D1D5DB"
        scale_bg = "#E5E7EB"
        mogged_color = (0, 0, 0, 180)
        mogged_text_color = "#E53E3E"
    else:
        bg_color = "#0E0E12"
        text_primary = "#F3F4F6"
        text_secondary = "#9CA3AF"
        text_tertiary = "#6B6B80"
        accent = "#10B981"
        line_color = "#2A2A3A"
        scale_bg = "#2A2A3A"
        mogged_color = (0, 0, 0, 180)
        mogged_text_color = "#E53E3E"

    canvas_w, canvas_h = 1300, 1300
    image = Image.new("RGBA", (canvas_w, canvas_h), bg_color)
    draw = ImageDraw.Draw(image)
    font_title = load_font(34)
    font_psl_num = load_font(56)
    font_sub = load_font(24)
    font_text = load_font(18)
    font_scale = load_font(16)
    font_winner = load_font(30)
    font_mogged = load_font(48)

    draw.text((canvas_w // 2, 25), title, fill=text_tertiary, font=font_title, anchor="mm")
    draw.line([(40, 70), (canvas_w - 40, 70)], fill=line_color, width=1)

    col_width = 550
    left_x = 50
    right_x = canvas_w - 50 - col_width
    photo_y = 110
    photo_width = col_width
    photo_height = 500

    def paste_rounded(img_bytes: bytes, x: int, y: int, w: int, h: int, radius: int = 28) -> tuple[int, int, int, int]:
        im = Image.open(BytesIO(img_bytes)).convert("RGBA")
        im.thumbnail((w, h), Image.Resampling.LANCZOS)
        ix = x + (w - im.width) // 2
        iy = y + (h - im.height) // 2
        mask = Image.new("L", im.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0) + im.size, radius=radius, fill=255)
        rounded = Image.new("RGBA", im.size, (0, 0, 0, 0))
        rounded.paste(im, (0, 0), mask=mask)
        image.paste(rounded, (ix, iy), rounded)
        return ix, iy, im.width, im.height

    left_rect = paste_rounded(p1, left_x, photo_y, photo_width, photo_height)
    right_rect = paste_rounded(p2, right_x, photo_y, photo_width, photo_height)

    winner_num = str(data.get("winner", "1"))
    loser_num = "2" if winner_num == "1" else "1"
    loser_rect = left_rect if loser_num == "1" else right_rect
    strip_height = 80
    strip_y = loser_rect[1] + (loser_rect[3] - strip_height) // 2
    overlay = Image.new("RGBA", (loser_rect[2], strip_height), mogged_color)
    image.paste(overlay, (loser_rect[0], strip_y), overlay)
    draw.text((loser_rect[0] + loser_rect[2] // 2, strip_y + strip_height // 2),
              mogged_text, fill=mogged_text_color, font=font_mogged, anchor="mm")

    winner_rect = left_rect if winner_num == "1" else right_rect
    winner_y = photo_y + photo_height + 30
    draw.text((winner_rect[0] + winner_rect[2] // 2, winner_y),
              winner_label, fill=accent, font=font_winner, anchor="mm")

    info_y = winner_y + 70
    for side, rect, key in [(1, left_rect, "photo1"), (2, right_rect, "photo2")]:
        pd = data.get(key, {})
        psl = pd.get("psl", "N/A")
        tier = pd.get("tier", "N/A")
        gender = pd.get("gender", "N/A")
        factors = pd.get("factors", {})
        if side == 1:
            anchor = "ls"
            bar_x = rect[0]
        else:
            anchor = "rs"
            bar_x = rect[0] + rect[2]
        draw.text((bar_x, info_y), f"PSL: {psl}", fill=text_primary, font=font_psl_num, anchor=anchor)
        draw.text((bar_x, info_y + 50), f"{tier} · {gender}", fill=accent, font=font_sub, anchor=anchor)
        try:
            psl_val = float(psl)
        except (ValueError, TypeError):
            psl_val = 1.0
        psl_val = max(1.0, min(8.0, psl_val))
        bar_w = rect[2]
        bar_y = info_y + 95
        bar_h = 20
        if side == 1:
            draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), radius=10, fill=scale_bg)
            fw = int((psl_val - 1) / 7 * bar_w)
            if fw > 0:
                draw.rounded_rectangle((bar_x, bar_y, bar_x + fw, bar_y + bar_h),
                                       radius=10, fill=get_tier_color(tier))
            for i in range(1, 9):
                x = bar_x + (i - 1) / 7 * bar_w
                draw.line([(x, bar_y - 6), (x, bar_y)], fill=text_tertiary, width=1)
                bbox = draw.textbbox((0, 0), str(i), font=font_scale)
                tw = bbox[2] - bbox[0]
                draw.text((x - tw / 2, bar_y - 24), str(i), fill=text_secondary, font=font_scale)
        else:
            draw.rounded_rectangle((bar_x - bar_w, bar_y, bar_x, bar_y + bar_h), radius=10, fill=scale_bg)
            fw = int((psl_val - 1) / 7 * bar_w)
            if fw > 0:
                draw.rounded_rectangle((bar_x - fw, bar_y, bar_x, bar_y + bar_h),
                                       radius=10, fill=get_tier_color(tier))
            for i in range(1, 9):
                x = bar_x - (i - 1) / 7 * bar_w
                draw.line([(x, bar_y - 6), (x, bar_y)], fill=text_tertiary, width=1)
                bbox = draw.textbbox((0, 0), str(i), font=font_scale)
                tw = bbox[2] - bbox[0]
                draw.text((x - tw / 2, bar_y - 24), str(i), fill=text_secondary, font=font_scale)
        fy = bar_y + bar_h + 25
        for idx, (fk, label) in enumerate(factor_labels.items()):
            if fk in factors:
                val = factors[fk]
                if isinstance(val, (int, float)):
                    val = str(val)
                draw.text((bar_x, fy + idx * 28), f"{label}: {val}",
                          fill=text_secondary, font=font_text, anchor=anchor)
    out = BytesIO()
    image.save(out, format="PNG")
    out.seek(0)
    return out


# ============================================================
# PSL AI DATA
# ============================================================
def _lookslike_not_a_face(data: JsonDict) -> bool:
    """Определяет, что на фото не человек (модель вернула N/A / 0.0 / спец-маркеры)."""
    tier = str(data.get("tier", "")).strip().upper()
    gender = str(data.get("gender", "")).strip().upper()
    if tier in ("N/A", "NA", "НЕТ", "-", "") and gender in ("N/A", "NA", "НЕТ", "-", ""):
        return True
    cons = data.get("cons")
    if isinstance(cons, list):
        joined = " ".join(str(c).lower() for c in cons)
        if ("не человек" in joined or "not a human" in joined or "not human" in joined
                or "иллюстрац" in joined or "animal" in joined or "object" in joined):
            return True
    summary = str(data.get("summary", "")).lower()
    if "не человек" in summary or "not a human" in summary or "not human" in summary:
        return True
    try:
        if float(data.get("psl", 0)) <= 0.0:
            return True
    except (TypeError, ValueError):
        pass
    return False


def _not_a_face_result(lang: str, data: JsonDict) -> dict[str, Any]:
    """Дружелюбный ответ вместо ошибки парсинга, когда на фото не человек."""
    cons = data.get("cons")
    hint = ""
    if isinstance(cons, list) and cons:
        hint = "; ".join(str(c) for c in cons[:2])
    elif data.get("summary"):
        hint = str(data["summary"])[:160]
    if lang == "ru":
        msg = ("🤔 на фото не человек — тут нечего оценивать по PSL. "
               "кин настоящую фотку лица, и разберём по полочкам.")
        if hint:
            msg += f"\n\n> {hint}"
    else:
        msg = ("🤔 that's not a human face — nothing to rate on the PSL scale. "
               "Send a real photo of a face and we'll break it down.")
        if hint:
            msg += f"\n\n> {hint}"
    return {"not_a_face": True, "message": msg}


async def get_looksmaxxing_data(
    photo_bytes: bytes,
    include_advice: bool,
    lang: str = "en",
    chat_id: int = 0,
    user_id: int = 0,
    platform: str = "tg",
) -> dict[str, Any]:
    if lang == "ru":
        prompt = (
            "Ты — чрезвычайно строгий AI-аналитик по looksmaxxing. Оцени лицо критически. "
            "Определи пол, кожу, волосы, костную структуру, челюсть, глаза, одутловатость, симметрию, кантальный наклон. "
            "Кратко, пару слов в каждом поле JSON. Рассчитай PSL от 1.0 до 8.0.\n\n"
            f"{TIER_RULES_STRICT}\n\n"
            "Диапазоны PSL: SUB 3: 1.0–2.4; SUB 5: 2.5–3.9; LTN/LTB: 4.0–5.5; MTN/MTB: 5.6–6.3; HTN/HTB: 6.4–6.9; "
            "CHADLITE/STACYLITE: 7.0–7.4; CHAD/STACY: 7.5–7.6; ADAMLITE/EVELITE: 7.7–7.8; TRUE ADAM/TRUE EVE: 7.9–8.0.\n\n"
            "Также оцени потенциал (максимально возможный тир). "
            "Верни ТОЛЬКО валидный JSON без markdown. Поля: "
            '"gender", "psl", "tier", "potential", "skin", "eyes", "jawline", "bloat", "hair", "bone_structure", '
            '"symmetry", "canthal_tilt", "pros" (массив 2-3), "cons" (массив 2-3), "summary"'
            + (', "advice" (советы).' if include_advice else ', "advice": ""')
        )
    else:
        prompt = (
            "You are an extremely strict and objective AI looksmaxxing analyst. Evaluate the face critically. "
            "Determine gender, skin, hair, bone structure, jawline, eyes, bloat, symmetry, canthal tilt. Brief fields. "
            "PSL 1.0-8.0.\n\n"
            f"{TIER_RULES_STRICT}\n\n"
            "PSL ranges: SUB 3: 1.0–2.4; SUB 5: 2.5–3.9; LTN/LTB: 4.0–5.5; MTN/MTB: 5.6–6.3; HTN/HTB: 6.4–6.9; "
            "CHADLITE/STACYLITE: 7.0–7.4; CHAD/STACY: 7.5–7.6; ADAMLITE/EVELITE: 7.7–7.8; TRUE ADAM/TRUE EVE: 7.9–8.0.\n\n"
            "Return ONLY valid JSON, no markdown. Fields: "
            '"gender", "psl", "tier", "potential", "skin", "eyes", "jawline", "bloat", "hair", "bone_structure", '
            '"symmetry", "canthal_tilt", "pros" (array 2-3), "cons" (array 2-3), "summary"'
            + (', "advice" (tips).' if include_advice else ', "advice": ""')
        )
    raw = await ask_ai_async(
        prompt=prompt, image_bytes=photo_bytes, image_mime="image/jpeg",
        system_instruction_override=(
            "You are a professional looksmaxxing AI. Answer ONLY with JSON. "
            "STRICT tier names only, no synonyms, no invented variants."
        ),
        chat_id=chat_id, user_id=user_id, platform=platform,
    )
    try:
        data = json_dict(json.loads(clean_json_text(raw)))
    except (json.JSONDecodeError, TypeError):
        logger.error(f"Looksmaxxing JSON decode: {raw[:200]}")
        return {"error": tr(lang, "ai_json_fail")}

    if _lookslike_not_a_face(data):
        return _not_a_face_result(lang, data)

    required = ("gender", "psl", "tier", "potential", "skin", "eyes", "jawline", "bloat",
                "hair", "bone_structure", "symmetry", "canthal_tilt", "pros", "cons", "summary")
    missing = [key for key in required if data.get(key) in (None, "", "N/A")]
    if missing:
        logger.error(f"Looksmaxxing response is incomplete ({missing}): {raw[:300]}")
        return {"error": tr(lang, "ai_json_fail")}
    return data


async def get_battle_data(p1: bytes, p2: bytes, lang: str = "en") -> dict[str, Any]:
    if lang == "ru":
        prompt = (
            "Ты — строгий AI-аналитик looksmaxxing. Сравни два лица, выбери победителя по PSL.\n\n"
            f"{TIER_RULES_STRICT}\n\n"
            "Верни JSON: photo1 {psl, tier, gender, factors {skin, eyes, jawline, bloat, hair, bone_structure, "
            "symmetry, canthal_tilt} (0-8), summary}, photo2 {...}, winner (\"1\" или \"2\"), reason. Без markdown. "
            "Только указанные названия тиров."
        )
    else:
        prompt = (
            "You are a strict looksmaxxing AI. Compare two faces, choose winner by PSL.\n\n"
            f"{TIER_RULES_STRICT}\n\n"
            "Return JSON: photo1 {psl, tier, gender, factors {skin, eyes, jawline, bloat, hair, bone_structure, "
            "symmetry, canthal_tilt} (0-8), summary}, photo2 {...}, winner (\"1\" or \"2\"), reason. No markdown. "
            "Only exact tier names. Do NOT invent new ones."
        )
    raw = await ask_ai_async(
        prompt=prompt,
        system_instruction_override=(
            "You are a looksmaxxing AI that outputs only JSON. STRICT tier names only: "
            f"male = {TIER_RULES_M}; female = {TIER_RULES_F}. "
            "Never use 'High Normie', 'Low Tier Normie', 'Subhuman', 'Animal', etc."
        ),
        image_bytes_list=[p1, p2], image_mime_list=["image/jpeg", "image/jpeg"],
    )
    try:
        return json_dict(json.loads(clean_json_text(raw)))
    except json.JSONDecodeError:
        logger.error(f"Battle JSON decode: {raw[:200]}")
        return {"error": tr(lang, "ai_json_fail")}


# ============================================================
# FEMBOY INFOGRAPHIC
# ============================================================
async def create_femboy_infographic(photo_bytes: bytes, data: JsonDict,
                                    theme: str = "dark", lang: str = "ru") -> BytesIO:
    if lang == "ru":
        title_text = "ОТЧЁТ FEMBOY RATE"
        fmb_label = "FMB"
        strengths_label = "ПРЕИМУЩЕСТВ."
        weaknesses_label = "НЕДОСТАТКИ"
        full_analysis_text = "Полный анализ в сообщении"
        metric_names = {"softness": "Мягкость", "hair": "Волосы", "style": "Стиль",
                        "build": "Телосложение", "expression": "Выражение",
                        "skin": "Кожа", "charm": "Обаяние", "voice_vibe": "Вайб голоса"}
        better_than_fmt = "Вы нежнее {}% людей"
        distribution_caption = "Распределение FMB"
        potential_label = "Потенциал:"
    else:
        title_text = "FEMBOY RATE REPORT"
        fmb_label = "FMB"
        strengths_label = "STRENGTHS"
        weaknesses_label = "WEAKNESSES"
        full_analysis_text = "Full analysis in the message"
        metric_names = {"softness": "Softness", "hair": "Hair", "style": "Style",
                        "build": "Build", "expression": "Expression",
                        "skin": "Skin", "charm": "Charm", "voice_vibe": "Voice vibe"}
        better_than_fmt = "Softer than {}% of people"
        distribution_caption = "FMB distribution"
        potential_label = "Potential:"

    if theme == "light":
        bg_color = "#F9F9FB"
        text_primary = "#1A1A2E"
        text_secondary = "#4A4A6A"
        text_tertiary = "#6B6B80"
        accent = "#9F7AEA"
        line_color = "#E5D6F5"
        scale_bg = "#E5E7EB"
        weak_color = "#C53030"
        highlight_outline = "#1A1A2E"
    else:
        bg_color = "#0E0E12"
        text_primary = "#F3F4F6"
        text_secondary = "#9CA3AF"
        text_tertiary = "#6B6B80"
        accent = "#B794F4"
        line_color = "#2A2A3A"
        scale_bg = "#2A2A3A"
        weak_color = "#E53E3E"
        highlight_outline = "#FFFFFF"

    canvas_w, canvas_h = 1000, 1000
    image = Image.new("RGBA", (canvas_w, canvas_h), bg_color)
    draw = ImageDraw.Draw(image)

    font_title = load_font(34)
    font_fmb_num = load_font(56)
    font_sub = load_font(24)
    font_text = load_font(18)
    font_small = load_font(15)
    font_scale = load_font(16)
    list_font = load_font(17)
    font_tier_label = load_font(13)

    draw.text((40, 25), title_text, fill=text_tertiary, font=font_title)
    draw.line([(40, 70), (canvas_w - 40, 70)], fill=line_color, width=1)

    user_img = Image.open(BytesIO(photo_bytes)).convert("RGBA")
    user_img.thumbnail((430, 530), Image.Resampling.LANCZOS)
    mask = Image.new("L", user_img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0) + user_img.size, radius=28, fill=255)
    rounded = Image.new("RGBA", user_img.size, (0, 0, 0, 0))
    rounded.paste(user_img, (0, 0), mask=mask)
    photo_x, photo_y = 40, 100
    image.paste(rounded, (photo_x, photo_y), rounded)

    fmb_score = data.get("fmb", data.get("psl", "N/A"))
    tier_name = str(data.get("tier", "N/A")).upper()
    gender = data.get("gender", "N/A")
    potential = data.get("potential", "N/A")
    try:
        fmb_val = max(1.0, min(10.0, float(str(fmb_score))))
    except (ValueError, TypeError):
        fmb_val = 1.0

    current_tier_idx = -1
    fk = find_femboy_tier_key(tier_name)
    if fk:
        for idx, t in enumerate(FEMBOY_TIER_DISTRIBUTION):
            if t["key"] == fk:
                current_tier_idx = idx
                break
    if current_tier_idx == -1:
        for idx, t in enumerate(FEMBOY_TIER_DISTRIBUTION):
            if float(t["fmb_low"]) <= fmb_val <= float(t["fmb_high"]):
                current_tier_idx = idx
                break
    if current_tier_idx == -1:
        current_tier_idx = 4

    better_than = max(0.1, min(99.9, (fmb_val - 1) / 9 * 100))
    better_text = better_than_fmt.format(round(better_than, 1))
    photo_bottom = photo_y + rounded.size[1]
    draw.text((40, photo_bottom + 20), better_text, fill=text_secondary, font=font_sub)

    chart_x = 40
    chart_y = photo_bottom + 65
    chart_width = 430
    chart_height = 20
    total_range = 10.0 - 1.0
    for tier in FEMBOY_TIER_DISTRIBUTION:
        low = float(tier["fmb_low"])
        high = float(tier["fmb_high"])
        tier_key = str(tier["key"])
        tier_short = str(tier["short"])
        x_start = chart_x + (low - 1.0) / total_range * chart_width
        x_end = chart_x + (high - 1.0) / total_range * chart_width
        draw.rectangle((x_start, chart_y, x_end, chart_y + chart_height),
                       fill=get_femboy_tier_color(tier_key))
        if tier_key == str(FEMBOY_TIER_DISTRIBUTION[current_tier_idx]["key"]):
            draw.rectangle([x_start - 1, chart_y - 1, x_end + 1, chart_y + chart_height + 1],
                           outline=highlight_outline, width=2)
        tb = draw.textbbox((0, 0), tier_short, font=font_tier_label)
        tw = tb[2] - tb[0]
        draw.text(((x_start + x_end) / 2 - tw / 2, chart_y + chart_height + 4),
                  tier_short, fill=text_secondary, font=font_tier_label)
    draw.text((40, chart_y + chart_height + 30), distribution_caption, fill=text_tertiary, font=font_small)

    start_x = 510
    right_top_y = 100
    draw.text((start_x, right_top_y), fmb_label, fill=text_tertiary, font=font_sub)
    draw.text((start_x, right_top_y + 35), f"{fmb_score}", fill=text_primary, font=font_fmb_num)
    draw.text((start_x, right_top_y + 110), f"{tier_name} · {gender}", fill=accent, font=font_sub)
    draw.text((start_x, right_top_y + 145), f"{potential_label} {potential}", fill=text_secondary, font=font_small)

    psl_bar_x, psl_bar_y = start_x, right_top_y + 200
    psl_bar_w, psl_bar_h = 400, 20
    draw.rounded_rectangle((psl_bar_x, psl_bar_y, psl_bar_x + psl_bar_w, psl_bar_y + psl_bar_h),
                           radius=10, fill=scale_bg)
    fw = int((fmb_val - 1) / 9 * psl_bar_w)
    if fw > 0:
        draw.rounded_rectangle((psl_bar_x, psl_bar_y, psl_bar_x + fw, psl_bar_y + psl_bar_h),
                               radius=10, fill=get_femboy_tier_color(tier_name))
    for i in range(1, 11):
        x = psl_bar_x + (i - 1) / 9 * psl_bar_w
        draw.line([(x, psl_bar_y - 6), (x, psl_bar_y)], fill=text_tertiary, width=1)
        bbox = draw.textbbox((0, 0), str(i), font=font_scale)
        tw = bbox[2] - bbox[0]
        draw.text((x - tw / 2, psl_bar_y - 24), str(i), fill=text_secondary, font=font_scale)

    metrics_mapping = [
        ("softness", data.get("softness", "N/A")), ("hair", data.get("hair", "N/A")),
        ("style", data.get("style", "N/A")), ("build", data.get("build", "N/A")),
        ("expression", data.get("expression", "N/A")), ("skin", data.get("skin", "N/A")),
        ("charm", data.get("charm", "N/A")), ("voice_vibe", data.get("voice_vibe", "N/A")),
    ]
    right_margin = start_x + 430
    col1_x = start_x
    col1_width = 200
    col2_x = col1_x + col1_width + 20
    col2_width = right_margin - col2_x
    base_row_height = 38
    min_padding = 6
    line_spacing = 2
    current_y = float(psl_bar_y + psl_bar_h + 25)
    for key, val_str in metrics_mapping:
        title = metric_names.get(key, key)
        tb = draw.textbbox((0, 0), title, font=font_text)
        title_h = tb[3] - tb[1]
        val_lines = wrap_text(str(val_str), draw, font_text, col2_width)
        val_block_h = block_height(val_lines, font_text, line_spacing, draw)
        row_height = max(base_row_height, title_h + 2 * min_padding, val_block_h + 2 * min_padding)
        draw.line([(col1_x, current_y), (right_margin, current_y)], fill=line_color, width=1)
        draw.text((col1_x, current_y + (row_height - title_h) / 2), title, fill=text_secondary, font=font_text)
        val_y = float(current_y) + (row_height - val_block_h) / 2
        for line in val_lines:
            bbox = draw.textbbox((0, 0), line, font=font_text)
            lh = bbox[3] - bbox[1]
            draw.text((col2_x, val_y), line, fill=text_primary, font=font_text)
            val_y += float(lh) + line_spacing
        current_y += float(row_height)
    draw.line([(col1_x, current_y), (right_margin, current_y)], fill=line_color, width=1)

    raw_pros = data.get("pros", [])
    raw_cons = data.get("cons", [])
    if isinstance(raw_pros, str):
        raw_pros = [raw_pros]
    if isinstance(raw_cons, str):
        raw_cons = [raw_cons]
    pros: list[str] = []
    cons: list[str] = []
    if isinstance(raw_pros, list):
        pros = [add_bullet(str(p)) for p in cast(list[object], raw_pros)]
    if isinstance(raw_cons, list):
        cons = [add_bullet(str(c)) for c in cast(list[object], raw_cons)]
    col_y = current_y + 20
    draw.text((start_x, col_y), strengths_label, fill=accent, font=font_sub)
    draw.text((start_x + 220, col_y), weaknesses_label, fill=weak_color, font=font_sub)
    col_width = 200
    line_height = 26
    list_start_y = col_y + 38

    def render_list(items: list[str], x: int, y: int, color: str, max_width: int = col_width) -> int:
        cy = y
        for item in items:
            for line in wrap_text(item, draw, list_font, max_width):
                draw.text((x, cy), line, fill=color, font=list_font)
                cy += line_height
            cy += 4
        return cy

    end_left = render_list(pros, start_x + 10, int(list_start_y), text_primary)
    end_right = render_list(cons, start_x + 230, int(list_start_y), text_primary)
    max_y = max(end_left, end_right)
    draw.text((40, max_y + 30), full_analysis_text, fill=text_tertiary, font=font_small)
    out = BytesIO()
    image.save(out, format="PNG")
    out.seek(0)
    return out


# ============================================================
# FEMBOY BATTLE
# ============================================================
async def create_femboy_battle_infographic(
    p1: bytes, p2: bytes, data: JsonDict, theme: str = "dark", lang: str = "ru",
) -> BytesIO:
    if lang == "ru":
        title = "БАТТЛ FEMBOY RATE"
        factor_labels = {"softness": "Мягкость", "hair": "Волосы", "style": "Стиль",
                         "build": "Телосложение", "expression": "Выражение",
                         "skin": "Кожа", "charm": "Обаяние", "voice_vibe": "Вайб голоса"}
        mogged_text = "ЗАМОГГАН"
        winner_label = "НЕЖНЕЙШИЙ"
    else:
        title = "FEMBOY RATE BATTLE"
        factor_labels = {"softness": "Softness", "hair": "Hair", "style": "Style",
                         "build": "Build", "expression": "Expression",
                         "skin": "Skin", "charm": "Charm", "voice_vibe": "Voice vibe"}
        mogged_text = "MOGGED"
        winner_label = "WINNER"

    if theme == "light":
        bg_color = "#F9F9FB"
        text_primary = "#1A1A2E"
        text_secondary = "#4A4A6A"
        text_tertiary = "#6B6B80"
        accent = "#9F7AEA"
        line_color = "#E5D6F5"
        scale_bg = "#E5E7EB"
        mogged_color = (0, 0, 0, 180)
        mogged_text_color = "#E53E3E"
    else:
        bg_color = "#0E0E12"
        text_primary = "#F3F4F6"
        text_secondary = "#9CA3AF"
        text_tertiary = "#6B6B80"
        accent = "#B794F4"
        line_color = "#2A2A3A"
        scale_bg = "#2A2A3A"
        mogged_color = (0, 0, 0, 180)
        mogged_text_color = "#E53E3E"

    canvas_w, canvas_h = 1300, 1300
    image = Image.new("RGBA", (canvas_w, canvas_h), bg_color)
    draw = ImageDraw.Draw(image)
    font_title = load_font(34)
    font_fmb_num = load_font(56)
    font_sub = load_font(24)
    font_text = load_font(18)
    font_scale = load_font(16)
    font_winner = load_font(30)
    font_mogged = load_font(48)

    draw.text((canvas_w // 2, 25), title, fill=text_tertiary, font=font_title, anchor="mm")
    draw.line([(40, 70), (canvas_w - 40, 70)], fill=line_color, width=1)

    col_width = 550
    left_x = 50
    right_x = canvas_w - 50 - col_width
    photo_y = 110
    photo_width = col_width
    photo_height = 500

    def paste_rounded(img_bytes: bytes, x: int, y: int, w: int, h: int, radius: int = 28) -> tuple[int, int, int, int]:
        im = Image.open(BytesIO(img_bytes)).convert("RGBA")
        im.thumbnail((w, h), Image.Resampling.LANCZOS)
        ix = x + (w - im.width) // 2
        iy = y + (h - im.height) // 2
        mask = Image.new("L", im.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0) + im.size, radius=radius, fill=255)
        rounded = Image.new("RGBA", im.size, (0, 0, 0, 0))
        rounded.paste(im, (0, 0), mask=mask)
        image.paste(rounded, (ix, iy), rounded)
        return ix, iy, im.width, im.height

    left_rect = paste_rounded(p1, left_x, photo_y, photo_width, photo_height)
    right_rect = paste_rounded(p2, right_x, photo_y, photo_width, photo_height)

    winner_num = str(data.get("winner", "1"))
    loser_num = "2" if winner_num == "1" else "1"
    loser_rect = left_rect if loser_num == "1" else right_rect
    strip_height = 80
    strip_y = loser_rect[1] + (loser_rect[3] - strip_height) // 2
    overlay = Image.new("RGBA", (loser_rect[2], strip_height), mogged_color)
    image.paste(overlay, (loser_rect[0], strip_y), overlay)
    draw.text((loser_rect[0] + loser_rect[2] // 2, strip_y + strip_height // 2),
              mogged_text, fill=mogged_text_color, font=font_mogged, anchor="mm")

    winner_rect = left_rect if winner_num == "1" else right_rect
    winner_y = photo_y + photo_height + 30
    draw.text((winner_rect[0] + winner_rect[2] // 2, winner_y),
              winner_label, fill=accent, font=font_winner, anchor="mm")

    info_y = winner_y + 70
    for side, rect, key in [(1, left_rect, "photo1"), (2, right_rect, "photo2")]:
        pd = data.get(key, {})
        fmb = pd.get("fmb", pd.get("psl", "N/A"))
        tier = pd.get("tier", "N/A")
        gender = pd.get("gender", "N/A")
        factors = pd.get("factors", {})
        if side == 1:
            anchor = "ls"
            bar_x = rect[0]
        else:
            anchor = "rs"
            bar_x = rect[0] + rect[2]
        draw.text((bar_x, info_y), f"FMB: {fmb}", fill=text_primary, font=font_fmb_num, anchor=anchor)
        draw.text((bar_x, info_y + 50), f"{tier} · {gender}", fill=accent, font=font_sub, anchor=anchor)
        try:
            fmb_val = float(fmb)
        except (ValueError, TypeError):
            fmb_val = 1.0
        fmb_val = max(1.0, min(10.0, fmb_val))
        bar_w = rect[2]
        bar_y = info_y + 95
        bar_h = 20
        if side == 1:
            draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), radius=10, fill=scale_bg)
            fw = int((fmb_val - 1) / 9 * bar_w)
            if fw > 0:
                draw.rounded_rectangle((bar_x, bar_y, bar_x + fw, bar_y + bar_h),
                                       radius=10, fill=get_femboy_tier_color(tier))
            for i in range(1, 11):
                x = bar_x + (i - 1) / 9 * bar_w
                draw.line([(x, bar_y - 6), (x, bar_y)], fill=text_tertiary, width=1)
                bbox = draw.textbbox((0, 0), str(i), font=font_scale)
                tw = bbox[2] - bbox[0]
                draw.text((x - tw / 2, bar_y - 24), str(i), fill=text_secondary, font=font_scale)
        else:
            draw.rounded_rectangle((bar_x - bar_w, bar_y, bar_x, bar_y + bar_h), radius=10, fill=scale_bg)
            fw = int((fmb_val - 1) / 9 * bar_w)
            if fw > 0:
                draw.rounded_rectangle((bar_x - fw, bar_y, bar_x, bar_y + bar_h),
                                       radius=10, fill=get_femboy_tier_color(tier))
            for i in range(1, 11):
                x = bar_x - (i - 1) / 9 * bar_w
                draw.line([(x, bar_y - 6), (x, bar_y)], fill=text_tertiary, width=1)
                bbox = draw.textbbox((0, 0), str(i), font=font_scale)
                tw = bbox[2] - bbox[0]
                draw.text((x - tw / 2, bar_y - 24), str(i), fill=text_secondary, font=font_scale)
        fy = bar_y + bar_h + 25
        for idx, (fk, label) in enumerate(factor_labels.items()):
            if fk in factors:
                val = factors[fk]
                if isinstance(val, (int, float)):
                    val = str(val)
                draw.text((bar_x, fy + idx * 28), f"{label}: {val}",
                          fill=text_secondary, font=font_text, anchor=anchor)
    out = BytesIO()
    image.save(out, format="PNG")
    out.seek(0)
    return out


# ============================================================
# FEMBOY AI DATA
# ============================================================
async def get_femboy_data(photo_bytes: bytes, include_advice: bool, lang: str = "ru") -> dict[str, Any]:
    if lang == "ru":
        prompt = (
            "Ты — AI-аналитик фембойности (Femboy Rate). Оцени по шкале FMB от 1.0 до 10.0, "
            "насколько человек выглядит как фембой / твай / нежный мягкий парень (или девушка — оцени как "
            "женскую версию по тем же критериям). Чем выше балл — тем более нежный, милый и феминный вайб.\n\n"
            "Учитывай: мягкость черт лица, длину и ухоженность волос, стиль одежды, телосложение, "
            "выражение лица, аккуратность, общее обаяние и вайб.\n\n"
            f"{FEMBOY_TIER_RULES_STRICT}\n\n"
            "Диапазоны FMB: CHAD 1.0–2.4; SIGMA 2.5–3.9; NORMIE 4.0–5.4; SOFTBOY/SOFTGIRL 5.5–6.4; "
            "CUTIE 6.5–7.4; FEMBOY/FEMGIRL 7.5–8.4; TWINK 8.5–9.2; ULTRAFEM 9.3–9.7; GODDESS 9.8–10.0.\n\n"
            "Также оцени потенциал (максимально возможный тир). "
            "Верни ТОЛЬКО валидный JSON без markdown. Поля: "
            '"gender", "fmb", "tier", "potential", "softness", "hair", "style", "build", "expression", '
            '"skin", "charm", "voice_vibe", "pros" (массив 2-3), "cons" (массив 2-3), "summary"'
            + (', "advice" (советы).' if include_advice else ', "advice": ""')
        )
    else:
        prompt = (
            "You are an AI femboy-ness analyst (Femboy Rate). Rate on the FMB scale from 1.0 to 10.0 how much "
            "the person looks like a femboy / twink / soft delicate guy (or a girl — rate by the same criteria). "
            "Higher = softer, cuter, more feminine vibe.\n\n"
            "Consider: softness of features, hair length & style, clothing style, build, expression, "
            "grooming, overall charm and vibe.\n\n"
            f"{FEMBOY_TIER_RULES_STRICT}\n\n"
            "FMB ranges: CHAD 1.0–2.4; SIGMA 2.5–3.9; NORMIE 4.0–5.4; SOFTBOY/SOFTGIRL 5.5–6.4; "
            "CUTIE 6.5–7.4; FEMBOY/FEMGIRL 7.5–8.4; TWINK 8.5–9.2; ULTRAFEM 9.3–9.7; GODDESS 9.8–10.0.\n\n"
            "Also estimate potential (highest possible tier). "
            "Return ONLY valid JSON, no markdown. Fields: "
            '"gender", "fmb", "tier", "potential", "softness", "hair", "style", "build", "expression", '
            '"skin", "charm", "voice_vibe", "pros" (array 2-3), "cons" (array 2-3), "summary"'
            + (', "advice" (tips).' if include_advice else ', "advice": ""')
        )
    raw = await ask_ai_async(
        prompt=prompt, image_bytes=photo_bytes, image_mime="image/jpeg",
        system_instruction_override=(
            "You are a femboy-ness AI. Answer ONLY with JSON. "
            "STRICT FMB tier names only, no synonyms, no invented variants."
        ),
    )
    try:
        return json_dict(json.loads(clean_json_text(raw)))
    except json.JSONDecodeError:
        logger.error(f"Femboy JSON decode: {raw[:200]}")
        return {"error": tr(lang, "ai_json_fail")}


async def get_femboy_battle_data(p1: bytes, p2: bytes, lang: str = "ru") -> dict[str, Any]:
    if lang == "ru":
        prompt = (
            "Ты — AI-аналитик фембойности. Сравни два фото и выбери, кто более нежный / феминный по шкале FMB.\n\n"
            f"{FEMBOY_TIER_RULES_STRICT}\n\n"
            "Верни JSON: photo1 {fmb, tier, gender, factors {softness, hair, style, build, expression, skin, "
            "charm, voice_vibe} (1-10), summary}, photo2 {...}, winner (\"1\" или \"2\"), reason. Без markdown. "
            "Только указанные названия тиров."
        )
    else:
        prompt = (
            "You are a femboy-ness AI. Compare two photos and pick who is softer / more feminine on the FMB scale.\n\n"
            f"{FEMBOY_TIER_RULES_STRICT}\n\n"
            "Return JSON: photo1 {fmb, tier, gender, factors {softness, hair, style, build, expression, skin, "
            "charm, voice_vibe} (1-10), summary}, photo2 {...}, winner (\"1\" or \"2\"), reason. No markdown. "
            "Only exact tier names."
        )
    raw = await ask_ai_async(
        prompt=prompt,
        system_instruction_override=(
            "You are a femboy-ness AI that outputs only JSON. STRICT FMB tier names only: "
            "CHAD, SIGMA, NORMIE, SOFTBOY, SOFTGIRL, CUTIE, FEMBOY, FEMGIRL, TWINK, ULTRAFEM, GODDESS."
        ),
        image_bytes_list=[p1, p2], image_mime_list=["image/jpeg", "image/jpeg"],
    )
    try:
        return json_dict(json.loads(clean_json_text(raw)))
    except json.JSONDecodeError:
        logger.error(f"Femboy battle JSON decode: {raw[:200]}")
        return {"error": tr(lang, "ai_json_fail")}