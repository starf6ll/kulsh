# Kulsh GPT | v2.40.0
# by (main author): starfall-apk
# coauthor & bot hosting: pomidorka1515

"""Pillow infographic engine (PSL-style dark/light card aesthetic)."""

import json
import math
import os
import re
from io import BytesIO
from typing import Any, cast

from PIL import Image, ImageDraw, ImageFont

from src.util import (
    ChartTheme,
    Color,
    Font,
    JsonDict,
    SeriesSpec,
    json_dict,
    theme_str,
    download_image_bytes,
    logger,
)

# ============================================================
# PALETTE
# ============================================================
_PALETTE = [
    "#10B981", "#4299E1", "#9F7AEA", "#F6AD55", "#FC8181",
    "#38B2AC", "#ED64A6", "#68D391", "#F6E05E", "#4FD1C5",
]

# ============================================================
# THEMES — соответствуют палитре PSL
# ============================================================
CHART_THEMES: dict[str, ChartTheme] = {
    "dark_modern": {
        "bg": "#0E0E12",
        "bg_grad": ("#13131C", "#0E0E12"),
        "text": "#F3F4F6",
        "text_dim": "#9CA3AF",
        "text_tertiary": "#6B6B80",
        "grid": "#2A2A3A",
        "accent": "#10B981",
        "card": "#14141C",
        "border": "#2A2A3A",
        "divider": "#2A2A3A",
    },
    "light_minimal": {
        "bg": "#F9F9FB",
        "bg_grad": ("#FFFFFF", "#F1F1F4"),
        "text": "#1A1A2E",
        "text_dim": "#4A4A6A",
        "text_tertiary": "#6B6B80",
        "grid": "#D1D5DB",
        "accent": "#2B6CB0",
        "card": "#FFFFFF",
        "border": "#E5E7EB",
        "divider": "#E5E7EB",
    },
    "ocean": {
        "bg": "#0A1929",
        "bg_grad": ("#103A5C", "#0A1929"),
        "text": "#E5F2FF",
        "text_dim": "#7FB1D6",
        "text_tertiary": "#5A8BB0",
        "grid": "#17334B",
        "accent": "#3FB0FF",
        "card": "#0F2538",
        "border": "#17334B",
        "divider": "#17334B",
    },
    "retro": {
        "bg": "#FBF6E9",
        "bg_grad": ("#FFF8E7", "#F0E2B6"),
        "text": "#2D2B22",
        "text_dim": "#6B6350",
        "text_tertiary": "#8B8470",
        "grid": "#D8CBA5",
        "accent": "#D97706",
        "card": "#FFFAEB",
        "border": "#D8CBA5",
        "divider": "#D8CBA5",
    },
}

DEFAULT_WIDTH = 900  # вертикальнее — как PSL


# ============================================================
# COLOR HELPERS
# ============================================================
def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = (h or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return (0, 0, 0)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (0, 0, 0)


def as_rgb(c: Color) -> tuple[int, int, int]:
    if isinstance(c, str):
        return hex_to_rgb(c)
    return (int(c[0]), int(c[1]), int(c[2]))


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*[max(0, min(255, int(c))) for c in rgb])


def lerp_color(c1: Color, c2: Color, t: float) -> tuple[int, int, int]:
    r1, g1, b1 = as_rgb(c1)
    r2, g2, b2 = as_rgb(c2)
    return (
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
    )


def darken(c: Color, factor: float = 0.7) -> tuple[int, int, int]:
    rgb = as_rgb(c)
    return (int(rgb[0] * factor), int(rgb[1] * factor), int(rgb[2] * factor))


def lighten(c: Color, factor: float = 1.3) -> tuple[int, int, int]:
    rgb = as_rgb(c)
    return (
        min(255, int(rgb[0] * factor)),
        min(255, int(rgb[1] * factor)),
        min(255, int(rgb[2] * factor)),
    )


def make_gradient_bg(w: int, h: int, c1: str, c2: str) -> Image.Image:
    base = Image.new("RGB", (1, h), hex_to_rgb(c1))
    for y in range(h):
        t = y / max(1, h - 1)
        base.putpixel((0, y), lerp_color(c1, c2, t))
    return base.resize((w, h), Image.Resampling.BILINEAR)  # pyright: ignore[reportUnknownMemberType]


def load_font(size: int, bold: bool = False) -> Font:
    candidates_bold = [
        os.path.join("fonts", "Montserrat-Bold.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "arialbd.ttf",
        "DejaVuSans-Bold.ttf",
    ]
    candidates_reg = [
        os.path.join("fonts", "Montserrat-Regular.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/Library/Fonts/Arial.ttf",
        "arial.ttf",
        "DejaVuSans.ttf",
    ]
    candidates = candidates_bold if bold else candidates_reg
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, font: Font) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text or " ", font=font)
    return int(bbox[2] - bbox[0]), int(bbox[3] - bbox[1])


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    xy_box: tuple[int, int, int, int],
    text: str,
    font: Font,
    fill: str | tuple[int, ...],
) -> None:
    x0, y0, x1, y1 = xy_box
    w, h = text_size(draw, text, font)
    x = x0 + (x1 - x0 - w) // 2
    y = y0 + (y1 - y0 - h) // 2
    draw.text((x, y), text, font=font, fill=fill)


def wrap_lines(draw: ImageDraw.ImageDraw, text: str, font: Font, max_width: int) -> list[str]:
    words = (text or "").split()
    lines: list[str] = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        tw, _ = text_size(draw, test, font)
        if tw <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def is_number(x: object) -> bool:
    try:
        float(cast(Any, x))
        return True
    except (TypeError, ValueError):
        return False


# ============================================================
# CARD HELPER
# ============================================================
def draw_card(canvas: Image.Image, box: tuple[int, int, int, int], theme: ChartTheme) -> None:
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(box, radius=18, fill=theme.get("card", "#14141C"),
                           outline=theme.get("border", "#2A2A3A"), width=1)


# ============================================================
# BAR
# ============================================================
def render_bar_chart(canvas: Image.Image, box: tuple[int, int, int, int],
                     spec: JsonDict, theme: ChartTheme) -> None:
    x0, y0, x1, y1 = box
    draw = ImageDraw.Draw(canvas)
    title = str(spec.get("title") or "")
    labels = [str(v) for v in spec.get("labels", [])]
    values = [float(v) for v in spec.get("values", []) if is_number(v)]
    if not values:
        return
    colors = spec.get("colors") or _PALETTE

    draw_card(canvas, box, theme)
    pad = 24
    cx0, cy0, cx1, cy1 = x0 + pad, y0 + pad, x1 - pad, y1 - pad
    font_title = load_font(20, bold=True)
    font_lab = load_font(12)
    font_val = load_font(13, bold=True)
    font_grid = load_font(10)

    if title:
        draw.text((cx0, cy0), title, font=font_title, fill=theme["text"])
        cy0 += 32

    chart_top = cy0 + 6
    chart_bottom = cy1 - 34
    chart_left = cx0 + 30
    chart_right = cx1 - 8
    if chart_bottom <= chart_top:
        return

    vmax = max(values) if values else 1.0
    vmax = vmax if vmax > 0 else 1.0
    mag = 10 ** int(math.floor(math.log10(vmax))) if vmax > 0 else 1
    nice_vmax = float(math.ceil(vmax / mag) * mag)
    if nice_vmax <= 0:
        nice_vmax = 1.0

    # grid + y labels
    steps = 4
    for i in range(steps + 1):
        yy = chart_bottom - int((chart_bottom - chart_top) * i / steps)
        val = nice_vmax * i / steps
        draw.line([(chart_left, yy), (chart_right, yy)], fill=theme["grid"], width=1)
        vs = f"{val:.2f}".rstrip("0").rstrip(".")
        draw.text((chart_left - 6 - text_size(draw, vs, font_grid)[0], yy - 5),
                  vs, font=font_grid, fill=theme["text_tertiary"])

    n = len(values)
    gap = 10
    total_w = chart_right - chart_left
    bar_w = max(6, int((total_w - gap * (n + 1)) / max(1, n)))

    for idx, val in enumerate(values):
        bx = chart_left + gap + idx * (bar_w + gap)
        bh = int((chart_bottom - chart_top) * (val / nice_vmax))
        by = chart_bottom - bh
        color = colors[idx % len(colors)]
        try:
            rgb = hex_to_rgb(str(color))
        except Exception:
            rgb = (16, 185, 129)
        if bh > 0:
            bar_img = Image.new("RGB", (bar_w, bh))
            for yy in range(bh):
                t = yy / max(1, bh - 1)
                bar_img.putpixel((0, yy), lerp_color(lighten(rgb, 1.2), rgb, t))
            bar_img = bar_img.resize((bar_w, bh), Image.Resampling.BILINEAR)  # pyright: ignore[reportUnknownMemberType]
            canvas.paste(bar_img, (bx, by))
        vs = f"{val:g}"
        vw, _ = text_size(draw, vs, font_val)
        draw.text((bx + (bar_w - vw) // 2, by - 18), vs, font=font_val, fill=theme["text"])
        lab = labels[idx] if idx < len(labels) else ""
        lab = lab[:12]
        lw, _ = text_size(draw, lab, font_lab)
        draw.text((bx + (bar_w - lw) // 2, chart_bottom + 8), lab,
                  font=font_lab, fill=theme["text_dim"])


# ============================================================
# LINE
# ============================================================
def render_line_chart(canvas: Image.Image, box: tuple[int, int, int, int],
                      spec: JsonDict, theme: ChartTheme) -> None:
    x0, y0, x1, y1 = box
    draw = ImageDraw.Draw(canvas)
    title = str(spec.get("title") or "")
    xs = [str(v) for v in spec.get("x", [])]
    series: list[Any] = spec.get("series") or []
    if not series:
        return

    norm: list[SeriesSpec] = []
    for s in series:
        if not isinstance(s, dict):
            continue
        sd = cast(JsonDict, s)
        ys = [float(v) for v in sd.get("y", []) if is_number(v)]
        if not ys:
            continue
        raw_color = sd.get("color")
        color = raw_color if isinstance(raw_color, str) else _PALETTE[len(norm) % len(_PALETTE)]
        raw_name = sd.get("name")
        norm.append({
            "name": raw_name if isinstance(raw_name, str) and raw_name else f"S{len(norm) + 1}",
            "y": ys,
            "color": color,
        })
    if not norm:
        return

    draw_card(canvas, box, theme)
    pad = 24
    cx0, cy0, cx1, cy1 = x0 + pad, y0 + pad, x1 - pad, y1 - pad
    font_title = load_font(20, bold=True)
    font_lab = load_font(11)
    font_grid = load_font(10)
    font_legend = load_font(11)

    if title:
        draw.text((cx0, cy0), title, font=font_title, fill=theme["text"])
        cy0 += 32

    # legend top-right
    legend_x = cx1
    legend_y = cy0 - 2
    for s in reversed(norm):
        name = str(s["name"])[:16]
        color = str(s["color"])
        tw, _ = text_size(draw, name, font_legend)
        legend_x -= tw + 20
        draw.line([(legend_x, legend_y + 8), (legend_x + 12, legend_y + 8)],
                  fill=hex_to_rgb(color), width=3)
        draw.text((legend_x + 16, legend_y), name, font=font_legend, fill=theme["text_dim"])

    chart_top = cy0 + 10
    chart_bottom = cy1 - 28
    chart_left = cx0 + 30
    chart_right = cx1 - 6
    if chart_bottom <= chart_top:
        return

    all_ys = [v for s in norm for v in cast(list[float], s["y"])]
    vmin = min(all_ys)
    vmax = max(all_ys)
    if vmax == vmin:
        vmax = vmin + 1
    pad_v = (vmax - vmin) * 0.1
    vmin -= pad_v
    vmax += pad_v

    steps = 4
    for i in range(steps + 1):
        yy = chart_bottom - int((chart_bottom - chart_top) * i / steps)
        val = vmin + (vmax - vmin) * i / steps
        draw.line([(chart_left, yy), (chart_right, yy)], fill=theme["grid"], width=1)
        vs = f"{val:.2f}".rstrip("0").rstrip(".")
        draw.text((chart_left - 6 - text_size(draw, vs, font_grid)[0], yy - 5),
                  vs, font=font_grid, fill=theme["text_tertiary"])

    max_len = max(len(cast(list[float], s["y"])) for s in norm)
    if max_len < 2:
        max_len = 2
    x_step = (chart_right - chart_left) / (max_len - 1)

    def _y_to_px(v: float) -> int:
        return chart_bottom - int((v - vmin) / (vmax - vmin) * (chart_bottom - chart_top))

    for s in norm:
        color = str(s["color"])
        pts = [(chart_left + i * x_step, _y_to_px(v)) for i, v in enumerate(cast(list[float], s["y"]))]
        if len(pts) >= 2:
            draw.line(pts, fill=hex_to_rgb(color), width=3)
        for p in pts:
            r = 4
            draw.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r],
                         fill=hex_to_rgb(color), outline=theme["bg"], width=2)

    for i in range(max_len):
        lab = xs[i] if i < len(xs) else str(i + 1)
        lab = lab[:8]
        lx = chart_left + i * x_step
        lw, _ = text_size(draw, lab, font_lab)
        draw.text((lx - lw // 2, chart_bottom + 6), lab, font=font_lab, fill=theme["text_dim"])


# ============================================================
# PIE
# ============================================================
def render_pie_chart(canvas: Image.Image, box: tuple[int, int, int, int],
                     spec: JsonDict, theme: ChartTheme, depth: int = 0) -> None:
    x0, y0, x1, y1 = box
    draw = ImageDraw.Draw(canvas)
    title = str(spec.get("title") or "")
    labels = [str(v) for v in spec.get("labels", [])]
    values = [float(v) for v in spec.get("values", []) if is_number(v)]
    if not values:
        return
    colors = spec.get("colors") or _PALETTE
    total = sum(values)
    if total <= 0:
        return

    draw_card(canvas, box, theme)
    pad = 24
    cx0, cy0, cx1, cy1 = x0 + pad, y0 + pad, x1 - pad, y1 - pad
    font_title = load_font(20, bold=True)
    font_legend = load_font(12)
    font_pct = load_font(12, bold=True)

    if title:
        draw.text((cx0, cy0), title, font=font_title, fill=theme["text"])
        cy0 += 32

    # pie on left, legend on right
    inner_w = cx1 - cx0
    inner_h = cy1 - cy0
    side = min(int(inner_w * 0.55), inner_h)
    if side < 60:
        side = max(60, min(inner_w, inner_h))
    pcx = cx0 + side // 2 + 6
    pcy = cy0 + inner_h // 2
    px0 = pcx - side // 2
    py0 = pcy - side // 2
    px1 = px0 + side
    py1 = py0 + side

    start = -90.0
    legend_x = px1 + 30
    legend_y = cy0 + 12

    for idx, val in enumerate(values):
        extent = 360 * (val / total)
        color = colors[idx % len(colors)]
        try:
            rgb = hex_to_rgb(str(color))
        except Exception:
            rgb = hex_to_rgb(_PALETTE[idx % len(_PALETTE)])
        if depth > 0:
            for d in range(depth, 0, -1):
                draw.pieslice([px0, py0 + d, px1, py1 + d],
                              start, start + extent,
                              fill=darken(rgb, 0.55), outline=darken(rgb, 0.5))
        draw.pieslice([px0, py0, px1, py1], start, start + extent,
                      fill=rgb, outline=theme["bg"], width=2)
        start += extent

    for idx, val in enumerate(values):
        color = colors[idx % len(colors)]
        try:
            rgb = hex_to_rgb(str(color))
        except Exception:
            rgb = hex_to_rgb(_PALETTE[idx % len(_PALETTE)])
        pct = val / total * 100
        lab = labels[idx] if idx < len(labels) else f"Item {idx + 1}"
        pct_line = f"{pct:.1f}%"
        if legend_y + 22 > cy1:
            break
        draw.rectangle([legend_x, legend_y + 3, legend_x + 14, legend_y + 17], fill=rgb)
        draw.text((legend_x + 22, legend_y), lab[:22], font=font_legend, fill=theme["text"])
        pw_, _ = text_size(draw, pct_line, font_pct)
        draw.text((cx1 - pw_ - 4, legend_y), pct_line, font=font_pct, fill=theme["text_dim"])
        legend_y += 24


# ============================================================
# TABLE
# ============================================================
def render_table(canvas: Image.Image, box: tuple[int, int, int, int],
                 spec: JsonDict, theme: ChartTheme) -> None:
    x0, y0, x1, y1 = box
    draw = ImageDraw.Draw(canvas)
    title = str(spec.get("title") or "")
    headers = [str(h) for h in spec.get("headers", [])]
    rows = [[str(c) for c in row] for row in spec.get("rows", [])]
    if not headers and not rows:
        return

    draw_card(canvas, box, theme)
    pad = 22
    cx0, cy0, cx1, cy1 = x0 + pad, y0 + pad, x1 - pad, y1 - pad
    font_title = load_font(20, bold=True)
    font_head = load_font(13, bold=True)
    font_row = load_font(13)

    if title:
        draw.text((cx0, cy0), title, font=font_title, fill=theme["text"])
        cy0 += 32

    n_cols = max([len(headers)] + [len(r) for r in rows] + [1])
    col_w = (cx1 - cx0) // n_cols
    row_h = 28
    y_cur = cy0 + 4

    if headers:
        for i in range(n_cols):
            label = headers[i] if i < len(headers) else ""
            cell_x0 = cx0 + i * col_w
            cell_x1 = cell_x0 + col_w
            draw.rectangle([cell_x0, y_cur, cell_x1, y_cur + row_h], fill=theme["accent"])
            draw_centered_text(draw, (cell_x0 + 6, y_cur, cell_x1 - 6, y_cur + row_h),
                               label, font_head, "#FFFFFF")
        y_cur += row_h

    for r_i, r in enumerate(rows):
        if y_cur + row_h > cy1:
            break
        row_bg = theme["bg"] if r_i % 2 == 0 else theme["card"]
        draw.rectangle([cx0, y_cur, cx1, y_cur + row_h], fill=row_bg)
        for i in range(n_cols):
            cell = r[i] if i < len(r) else ""
            cell_x0 = cx0 + i * col_w
            cell_x1 = cell_x0 + col_w
            draw_centered_text(draw, (cell_x0 + 6, y_cur, cell_x1 - 6, y_cur + row_h),
                               cell[:36], font_row, theme["text"])
        draw.line([(cx0, y_cur + row_h), (cx1, y_cur + row_h)], fill=theme["grid"], width=1)
        y_cur += row_h


# ============================================================
# IMAGE
# ============================================================
async def load_remote_image(url: str) -> Image.Image | None:
    try:
        data = await download_image_bytes(url)
        return Image.open(BytesIO(data)).convert("RGBA")
    except Exception as e:
        logger.warning(f"load_remote_image err: {e}")
        return None


def render_image_block(canvas: Image.Image, box: tuple[int, int, int, int],
                       img: Image.Image, theme: ChartTheme) -> None:
    x0, y0, x1, y1 = box
    draw_card(canvas, box, theme)
    inner = 12
    ix0, iy0, ix1, iy1 = x0 + inner, y0 + inner, x1 - inner, y1 - inner
    box_w = ix1 - ix0
    box_h = iy1 - iy0
    if box_w <= 0 or box_h <= 0:
        return
    im = img.copy()
    im.thumbnail((box_w, box_h), Image.Resampling.LANCZOS)
    ox = ix0 + (box_w - im.width) // 2
    oy = iy0 + (box_h - im.height) // 2
    if im.mode == "RGBA":
        canvas.paste(im, (ox, oy), im)
    else:
        canvas.paste(im, (ox, oy))


# ============================================================
# RENDER INFOGRAPHIC
# ============================================================
async def render_infographic(spec: JsonDict, user_images: list[bytes] | None = None) -> BytesIO:
    """Строит инфографику в PSL-стиле: вертикальный аспект, аккуратные карточки."""
    theme_name = str(spec.get("theme", "dark_modern"))
    theme = CHART_THEMES.get(theme_name, CHART_THEMES["dark_modern"])

    width = int(spec.get("width", DEFAULT_WIDTH))
    width = max(600, min(1600, width))
    title = str(spec.get("title") or "")
    subtitle = str(spec.get("subtitle") or "")
    blocks: list[Any] = spec.get("blocks") or []

    # Preload images
    preloaded: dict[int, Image.Image] = {}
    for idx, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        b = cast(JsonDict, block)
        if b.get("type") == "image":
            src = b.get("source", "url")
            if src == "user" and user_images:
                i = int(b.get("index", 0))
                if 0 <= i < len(user_images):
                    try:
                        preloaded[idx] = Image.open(BytesIO(user_images[i])).convert("RGBA")
                    except Exception:
                        pass
            elif src == "url" and b.get("url"):
                img = await load_remote_image(str(b["url"]))
                if img is not None:
                    preloaded[idx] = img

    padding = 36
    inner_w = width - padding * 2

    # fonts
    font_title = load_font(34, bold=True)
    font_sub = load_font(16)
    font_h = load_font(22, bold=True)
    font_text = load_font(16)

    tmp_img = Image.new("RGB", (10, 10))
    tmp_draw = ImageDraw.Draw(tmp_img)

    heights: list[int] = []
    for idx, block in enumerate(blocks):
        if not isinstance(block, dict):
            heights.append(0)
            continue
        b = cast(JsonDict, block)
        t = b.get("type", "text")
        if t == "heading":
            heights.append(40)
        elif t == "text":
            lines = wrap_lines(tmp_draw, str(b.get("text", "")), font_text, inner_w)
            heights.append(max(28, len(lines) * 22 + 8))
        elif t == "divider":
            heights.append(28)
        elif t == "bar":
            heights.append(int(b.get("height", 340)))
        elif t == "line":
            heights.append(int(b.get("height", 340)))
        elif t == "pie":
            heights.append(int(b.get("height", 320)))
        elif t == "pie3d":
            heights.append(int(b.get("height", 340)))
        elif t == "table":
            n_rows = len(b.get("rows", []))
            n_head = 1 if b.get("headers") else 0
            heights.append(60 + (n_rows + n_head) * 28 + 20)
        elif t == "image":
            heights.append(int(b.get("height", 360)))
        else:
            heights.append(0)

    header_h = 0
    if title:
        header_h += 56
    if subtitle:
        header_h += 26

    total_h = padding * 2 + header_h + sum(heights) + max(0, len(blocks) - 1) * 16
    total_h = max(400, total_h)

    # background
    bg_grad = theme.get("bg_grad")
    grad: list[Any] = cast(list[Any], bg_grad) if isinstance(bg_grad, (tuple, list)) else []
    if len(grad) >= 2:
        bg_c1, bg_c2 = str(grad[0]), str(grad[1])
    else:
        bg_c1 = bg_c2 = theme_str(theme, "bg")
    canvas = make_gradient_bg(width, total_h, bg_c1, bg_c2).convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    # header
    y = padding
    if title:
        draw.text((padding, y), title, font=font_title, fill=theme_str(theme, "text_tertiary"))
        y += 48
    if subtitle:
        draw.text((padding, y), subtitle, font=font_sub, fill=theme_str(theme, "text_dim"))
        y += 24
    if title or subtitle:
        draw.line([(padding, y + 4), (width - padding, y + 4)],
                  fill=theme_str(theme, "divider"), width=1)
        y += 20

    # blocks
    for idx, block in enumerate(blocks):
        h = heights[idx]
        if h <= 0 or not isinstance(block, dict):
            continue
        box = (padding, y, width - padding, y + h)
        b = cast(JsonDict, block)
        t = b.get("type", "text")

        if t == "heading":
            draw.text((padding, y + 6), str(b.get("text", "")), font=font_h,
                      fill=theme_str(theme, "text"))
        elif t == "text":
            lines = wrap_lines(draw, str(b.get("text", "")), font_text, inner_w)
            ty = y + 4
            for line in lines:
                draw.text((padding, ty), line, font=font_text,
                          fill=theme_str(theme, "text"))
                ty += 22
        elif t == "divider":
            mid_y = y + h // 2
            draw.line([(padding + 10, mid_y), (width - padding - 10, mid_y)],
                      fill=theme_str(theme, "divider"), width=1)
        elif t == "bar":
            render_bar_chart(canvas, box, b, theme)
        elif t == "line":
            render_line_chart(canvas, box, b, theme)
        elif t == "pie":
            render_pie_chart(canvas, box, b, theme, depth=0)
        elif t == "pie3d":
            render_pie_chart(canvas, box, b, theme, depth=max(10, h // 24))
        elif t == "table":
            render_table(canvas, box, b, theme)
        elif t == "image":
            img = preloaded.get(idx)
            if img is not None:
                render_image_block(canvas, box, img, theme)

        y += h + 16

    out = BytesIO()
    canvas.convert("RGB").save(out, format="PNG", optimize=True)
    out.seek(0)
    return out


def extract_chart_marker(text: str) -> tuple[JsonDict | None, str]:
    if not text or "!chart" not in text:
        return None, text
    m = re.search(r'!chart\s*\n?```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
    if not m:
        idx = text.find("!chart")
        if idx >= 0:
            start = text.find("{", idx)
            if start >= 0:
                depth = 0
                end = -1
                in_str = False
                esc = False
                for i in range(start, len(text)):
                    c = text[i]
                    if esc:
                        esc = False
                        continue
                    if c == "\\":
                        esc = True
                        continue
                    if c == '"':
                        in_str = not in_str
                        continue
                    if in_str:
                        continue
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                if end > 0:
                    raw = text[start:end]
                    try:
                        spec = json_dict(json.loads(raw))
                        remaining = (text[:idx] + text[end:]).strip()
                        return spec, remaining
                    except Exception:
                        pass
        return None, text
    try:
        spec = json_dict(json.loads(m.group(1)))
        remaining = (text[:m.start()] + text[m.end():]).strip()
        return spec, remaining
    except Exception as e:
        logger.warning(f"chart json parse fail: {e}")
        return None, text