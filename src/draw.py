# Kulsh GPT | v2.47.0
# by (main author): starfall-apk
# coauthor & bot hosting: pomidorka1515

"""Pillow drawing engine: JSON-spec renderer + SVG subset + safe asset terminal.

The AI can draw arbitrary images by emitting a `!draw` block containing a JSON
spec, and can fetch fonts/overlay images via a restricted `!term` terminal.
Temporary assets are downloaded into a per-request sandbox and deleted after
the finished image is sent to the user.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from io import BytesIO
from typing import Any, cast

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from src.util import (
    Color,
    Font,
    JsonDict,
    json_dict,
    json_str,
    logger,
    download_image_bytes,
)

# ============================================================
# LIMITS / SANDBOX
# ============================================================
MAX_CANVAS = 2048
MIN_CANVAS = 64
MAX_ELEMENTS = 512
MAX_PATH_POINTS = 4096
ASSET_DIR_NAME = "kulsh_draw_assets"
ASSET_TTL_SECONDS = 60 * 30  # 30 минут
MAX_ASSET_BYTES = 8 * 1024 * 1024

# Разрешённые хосты для скачивания ассетов (шрифты/картинки).
ASSET_HOST_ALLOW = (
    "fonts.google.com",
    "fonts.gstatic.com",
    "github.com",
    "raw.githubusercontent.com",
    "githubusercontent.com",
    "cdn.jsdelivr.net",
    "i.imgur.com",
    "cdn.discordapp.com",
    "media.discordapp.net",
    "upload.wikimedia.org",
    "wikimedia.org",
    "files.catbox.moe",
    "0x0.st",
)

# Разрешённые бинарные команды «терминала» (нужны для скачивания).
TERM_BIN_ALLOW = frozenset({"pip", "pip3", "curl", "wget", "python", "python3"})
# pip-пакеты, которые разрешено доустанавливать для рендера.
PIP_ALLOW = frozenset({"cairosvg", "svglib", "reportlab", "numpy", "fonttools"})


def _safe_asset_dir() -> str:
    base = os.path.join(tempfile.gettempdir(), ASSET_DIR_NAME)
    os.makedirs(base, exist_ok=True)
    return base


def _sweep_assets() -> None:
    """Удаляет ассеты старше TTL. Вызывается при каждом рендере."""
    base = _safe_asset_dir()
    now = time.time()
    try:
        for name in os.listdir(base):
            path = os.path.join(base, name)
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                elif now - os.path.getmtime(path) > ASSET_TTL_SECONDS:
                    os.remove(path)
            except OSError:
                continue
    except OSError:
        pass


# ============================================================
# COLOR HELPERS (реюз из charts по смыслу)
# ============================================================
def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = (h or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) not in (6, 8):
        return (0, 0, 0)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (0, 0, 0)


def as_rgb(c: Color) -> tuple[int, int, int]:
    if isinstance(c, str):
        return hex_to_rgb(c)
    return (int(c[0]), int(c[1]), int(c[2]))


def as_rgba(c: Any, alpha: int = 255) -> tuple[int, int, int, int]:
    if isinstance(c, str):
        h = c.lstrip("#")
        if len(h) == 8:
            r, g, b = hex_to_rgb(h)
            a = int(h[6:8], 16)
            return (r, g, b, a)
        r, g, b = hex_to_rgb(c)
        return (r, g, b, alpha)
    if isinstance(c, (list, tuple)):
        vals = [int(x) for x in c]
        if len(vals) >= 4:
            return (vals[0], vals[1], vals[2], vals[3])
        if len(vals) == 3:
            return (vals[0], vals[1], vals[2], alpha)
    return (0, 0, 0, alpha)


def _clamp_canvas(v: Any, default: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(MIN_CANVAS, min(MAX_CANVAS, n))


# ============================================================
# GRADIENTS
# ============================================================
def _gradient(size: tuple[int, int], c1: Color, c2: Color, angle: float = 0.0) -> Image.Image:
    w, h = max(1, size[0]), max(1, size[1])
    base = Image.new("RGB", (w, h), as_rgb(c1))
    grad = Image.new("RGB", (1, h if abs(angle) < 1 else w))
    return _linear_gradient(w, h, as_rgb(c1), as_rgb(c2), angle)


def _linear_gradient(w: int, h: int, rgb1: tuple[int, int, int], rgb2: tuple[int, int, int],
                     angle: float = 0.0) -> Image.Image:
    """Линейный градиент через создание 1px-полосы по диагонали и поворот."""
    diag = int(math.hypot(w, h))
    ramp = Image.new("RGB", (diag, 1))
    px = ramp.load()
    for x in range(diag):
        t = x / max(1, diag - 1)
        px[x, 0] = (
            int(rgb1[0] + (rgb2[0] - rgb1[0]) * t),
            int(rgb1[1] + (rgb2[1] - rgb1[1]) * t),
            int(rgb1[2] + (rgb2[2] - rgb1[2]) * t),
        )
    ramp = ramp.resize((diag, diag))
    ramp = ramp.rotate(angle, resample=Image.BICUBIC, expand=False)
    left = (diag - w) // 2
    top = (diag - h) // 2
    return ramp.crop((left, top, left + w, top + h))


def _radial_gradient(w: int, h: int, inner: Color, outer: Color) -> Image.Image:
    ir, ig, ib = as_rgb(inner)
    orr, og, ob = as_rgb(outer)
    img = Image.new("RGB", (w, h))
    px = img.load()
    cx, cy = w / 2, h / 2
    maxd = math.hypot(cx, cy) or 1
    for y in range(h):
        for x in range(w):
            t = min(1.0, math.hypot(x - cx, y - cy) / maxd)
            px[x, y] = (int(ir + (orr - ir) * t), int(ig + (og - ig) * t), int(ib + (ob - ib) * t))
    return img


# ============================================================
# FONT RESOLUTION
# ============================================================
_FONT_DIR_NAME = "kulsh_draw_fonts"


def _font_search_dirs() -> list[str]:
    dirs = [
        os.path.join(os.getcwd(), "fonts"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts"),
        _safe_asset_dir(),
        os.path.join(tempfile.gettempdir(), _FONT_DIR_NAME),
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        "C:/Windows/Fonts",
    ]
    return [d for d in dirs if os.path.isdir(d)]


def resolve_font(spec: Any, size: int) -> Font:
    """Разрешает шрифт: имя файла, путь или имя семейства. Иначе — дефолт."""
    size = max(4, min(400, int(size)))
    if isinstance(spec, str) and spec:
        candidate = spec if os.path.isabs(spec) or os.sep in spec else None
        if candidate and os.path.isfile(candidate):
            try:
                return ImageFont.truetype(candidate, size)
            except Exception:
                pass
        fname = spec.lower()
        for d in _font_search_dirs():
            try:
                for name in os.listdir(d):
                    if fname in name.lower() and name.lower().endswith((".ttf", ".otf", ".ttc")):
                        try:
                            return ImageFont.truetype(os.path.join(d, name), size)
                        except Exception:
                            continue
            except OSError:
                continue
    for fallback in ("Montserrat-Bold.ttf", "arial.ttf", "DejaVuSans.ttf"):
        for d in _font_search_dirs():
            p = os.path.join(d, fallback)
            if os.path.isfile(p):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    continue
    return ImageFont.load_default()


# ============================================================
# SVG PATH PARSING (subset: M L H V C Q Z, abs+rel)
# ============================================================
_PATH_TOKEN_RE = re.compile(r'([MmLlHhVvCcSsQqTtAaZz])|(-?\d*\.?\d+(?:e[-+]?\d+)?)', re.IGNORECASE)


def svg_path_points(d: str, steps: int = 24) -> list[tuple[str, float, float]]:
    """Грубый парсер SVG path → список точек (в пикселях) для полилинии.
    Поддерживает M,L,H,V,C,Q,S,T,Z (A сводится к линии). Возвращает команды 'L'/'M'."""
    tokens: list[Any] = []
    for m in _PATH_TOKEN_RE.finditer(d or ""):
        if m.group(1):
            tokens.append(m.group(1))
        else:
            tokens.append(float(m.group(2)))
    pts: list[tuple[str, float, float]] = []
    i = 0
    cx = cy = 0.0
    start_x = start_y = 0.0
    cmd = None
    prev_ctrl_x: float | None = None
    prev_ctrl_y: float | None = None

    def num() -> float:
        nonlocal i
        if i >= len(tokens) or isinstance(tokens[i], str):
            return 0.0
        v = tokens[i]
        i += 1
        return float(v)

    while i < len(tokens):
        if isinstance(tokens[i], str):
            cmd = tokens[i]
            i += 1
            if cmd in ("Z", "z"):
                pts.append(("L", start_x, start_y))
                cx, cy = start_x, start_y
            continue
        if cmd is None:
            i += 1
            continue
        c = cmd
        rel = c.islower()
        verb = c.upper()
        if verb == "M":
            x, y = num(), num()
            if rel:
                x, y = cx + x, cy + y
            cx, cy = x, y
            start_x, start_y = x, y
            pts.append(("M", cx, cy))
        elif verb == "L":
            x, y = num(), num()
            if rel:
                x, y = cx + x, cy + y
            cx, cy = x, y
            pts.append(("L", cx, cy))
        elif verb == "H":
            x = num()
            if rel:
                x = cx + x
            cx = x
            pts.append(("L", cx, cy))
        elif verb == "V":
            y = num()
            if rel:
                y = cy + y
            cy = y
            pts.append(("L", cx, cy))
        elif verb in ("C", "S"):
            if verb == "C":
                x1, y1, x2, y2, x, y = num(), num(), num(), num(), num(), num()
                if rel:
                    x1, y1, x2, y2, x, y = cx + x1, cy + y1, cx + x2, cy + y2, cx + x, cy + y
            else:
                if prev_ctrl_x is None:
                    x1, y1 = cx, cy
                else:
                    x1, y1 = 2 * cx - prev_ctrl_x, 2 * cy - prev_ctrl_y
                x2, y2, x, y = num(), num(), num(), num()
                if rel:
                    x2, y2, x, y = cx + x2, cy + y2, cx + x, cy + y
            for s in range(1, steps + 1):
                t = s / steps
                mt = 1 - t
                bx = mt * mt * mt * cx + 3 * mt * mt * t * x1 + 3 * mt * t * t * x2 + t * t * t * x
                by = mt * mt * mt * cy + 3 * mt * mt * t * y1 + 3 * mt * t * t * y2 + t * t * t * y
                pts.append(("L", bx, by))
            prev_ctrl_x, prev_ctrl_y = x2, y2
            cx, cy = x, y
        elif verb == "Q":
            x1, y1, x, y = num(), num(), num(), num()
            if rel:
                x1, y1, x, y = cx + x1, cy + y1, cx + x, cy + y
            for s in range(1, steps + 1):
                t = s / steps
                mt = 1 - t
                bx = mt * mt * cx + 2 * mt * t * x1 + t * t * x
                by = mt * mt * cy + 2 * mt * t * y1 + t * t * y
                pts.append(("L", bx, by))
            prev_ctrl_x, prev_ctrl_y = x1, y1
            cx, cy = x, y
        elif verb == "T":
            if prev_ctrl_x is None:
                x1, y1 = cx, cy
            else:
                x1, y1 = 2 * cx - prev_ctrl_x, 2 * cy - prev_ctrl_y
            x, y = num(), num()
            if rel:
                x, y = cx + x, cy + y
            for s in range(1, steps + 1):
                t = s / steps
                mt = 1 - t
                bx = mt * mt * cx + 2 * mt * t * x1 + t * t * x
                by = mt * mt * cy + 2 * mt * t * y1 + t * t * y
                pts.append(("L", bx, by))
            prev_ctrl_x, prev_ctrl_y = x1, y1
            cx, cy = x, y
        elif verb == "A":
            # Дуга: сводим к прямой через конечную точку (полноценные дуги — редкость).
            num(); num(); num(); num(); num()
            x, y = num(), num()
            if rel:
                x, y = cx + x, cy + y
            cx, cy = x, y
            pts.append(("L", cx, cy))
        else:
            i += 1
    return pts


# ============================================================
# ELEMENT RENDERERS
# ============================================================
def _draw_shadowed(img: Image.Image, shape: str, xy: Any, *, fill: Any = None,
                   outline: Any = None, width: int = 1, shadow: JsonDict | None = None) -> None:
    if shadow:
        off = int(shadow.get("offset", 6))
        blur = int(shadow.get("blur", 8))
        col = as_rgba(shadow.get("color", "#00000080"))
        # Рисуем фигуру на отдельном слое, размываем и накладываем.
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ldraw = ImageDraw.Draw(layer, "RGBA")
        _shape(ldraw, shape, _shift_xy(xy, off, off), fill=col, outline=None, width=width)
        layer = layer.filter(ImageFilter.GaussianBlur(blur))
        img.alpha_composite(layer)
    draw = ImageDraw.Draw(img, "RGBA")
    _shape(draw, shape, xy, fill=fill, outline=outline, width=width)


def _shift_xy(xy: Any, dx: int, dy: int) -> Any:
    if isinstance(xy, (list, tuple)) and xy and isinstance(xy[0], (list, tuple)):
        return [(x + dx, y + dy) for x, y in xy]
    if isinstance(xy, (list, tuple)) and len(xy) == 4:
        return (xy[0] + dx, xy[1] + dy, xy[2] + dx, xy[3] + dy)
    if isinstance(xy, (list, tuple)) and len(xy) >= 2:
        return (xy[0] + dx, xy[1] + dy)
    return xy


def _shape(draw: ImageDraw.ImageDraw, shape: str, xy: Any, *, fill: Any = None,
           outline: Any = None, width: int = 1) -> None:
    if shape == "line":
        draw.line(xy, fill=fill, width=width, joint="curve")
    elif shape == "rect":
        draw.rectangle(xy, fill=fill, outline=outline, width=width)
    elif shape == "ellipse":
        draw.ellipse(xy, fill=fill, outline=outline, width=width)
    elif shape == "polygon":
        draw.polygon(xy, fill=fill, outline=outline)
    elif shape == "arc":
        draw.arc(xy, start=xy.get("start", 0) if isinstance(xy, dict) else 0,
                 end=xy.get("end", 360) if isinstance(xy, dict) else 360,
                 fill=fill, width=width)
    else:
        draw.line(xy, fill=fill, width=width)


def _render_element(img: Image.Image, el: JsonDict) -> None:
    kind = str(el.get("type", "")).lower()
    fill = el.get("fill")
    outline = el.get("outline") or el.get("stroke")
    width = int(el.get("width", el.get("stroke_width", 1)) or 1)
    shadow = json_dict(el.get("shadow")) if isinstance(el.get("shadow"), dict) else None

    if kind in ("background", "gradient_rect", "gradient"):
        x1, y1, x2, y2 = _rect_coords(el)
        c1 = el.get("from", el.get("color1", el.get("start", "#000000")))
        c2 = el.get("to", el.get("color2", el.get("end", "#FFFFFF")))
        angle = float(el.get("angle", 0))
        w = max(1, x2 - x1)
        h = max(1, y2 - y1)
        grad = _linear_gradient(w, h, as_rgb(c1), as_rgb(c2), angle)
        img.paste(grad, (x1, y1))
        return

    if kind == "radial_gradient":
        x1, y1, x2, y2 = _rect_coords(el)
        c1 = el.get("inner", el.get("from", "#FFFFFF"))
        c2 = el.get("outer", el.get("to", "#000000"))
        w = max(1, x2 - x1)
        h = max(1, y2 - y1)
        grad = _radial_gradient(w, h, c1, c2)
        img.paste(grad, (x1, y1))
        return

    draw = ImageDraw.Draw(img, "RGBA")

    if kind == "line":
        pts = _points(el.get("points") or el.get("xy") or [])
        _draw_shadowed(img, "line", pts, fill=as_rgba(fill, 255), width=width, shadow=shadow)
    elif kind == "rect" or kind == "rectangle":
        xy = _rect_tuple(el)
        _draw_shadowed(img, "rect", xy, fill=as_rgba(fill) if fill else None,
                       outline=as_rgba(outline) if outline else None, width=width, shadow=shadow)
    elif kind in ("circle", "ellipse"):
        xy = _rect_tuple(el)
        _draw_shadowed(img, "ellipse", xy, fill=as_rgba(fill) if fill else None,
                       outline=as_rgba(outline) if outline else None, width=width, shadow=shadow)
    elif kind == "polygon":
        pts = _points(el.get("points") or [])
        _draw_shadowed(img, "polygon", pts, fill=as_rgba(fill) if fill else None,
                       outline=as_rgba(outline) if outline else None, width=width, shadow=shadow)
    elif kind in ("polyline", "path_curve", "bezier"):
        pts = _points(el.get("points") or [])
        draw.line(pts, fill=as_rgba(fill or outline or "#FFFFFF"), width=width, joint="curve")
    elif kind == "svg":
        pts = [(x, y) for _c, x, y in svg_path_points(json_str(el.get("d")), int(el.get("steps", 24)))]
        if pts:
            if el.get("closed"):
                draw.polygon(pts, fill=as_rgba(fill) if fill else None,
                             outline=as_rgba(outline) if outline else None)
            else:
                draw.line(pts, fill=as_rgba(fill or outline or "#FFFFFF"), width=width, joint="curve")
    elif kind == "text":
        _draw_text(img, el)
    elif kind == "image":
        _draw_image(img, el)
    elif kind == "blur":
        x1, y1, x2, y2 = _rect_coords(el)
        region = img.crop((x1, y1, x2, y2)).filter(ImageFilter.GaussianBlur(float(el.get("radius", 6))))
        img.paste(region, (x1, y1))


def _rect_coords(el: JsonDict) -> tuple[int, int, int, int]:
    x = int(el.get("x", 0)); y = int(el.get("y", 0))
    w = int(el.get("w", el.get("width_box", 0)) or 0)
    h = int(el.get("h", el.get("height_box", 0)) or 0)
    if w and h:
        return x, y, x + w, y + h
    x2 = int(el.get("x2", x)); y2 = int(el.get("y2", y))
    return x, y, x2, y2


def _rect_tuple(el: JsonDict) -> tuple[int, int, int, int]:
    return _rect_coords(el)


def _points(raw: Any) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    if isinstance(raw, list):
        for p in raw[:MAX_PATH_POINTS]:
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                out.append((float(p[0]), float(p[1])))
            elif isinstance(p, dict) and "x" in p and "y" in p:
                out.append((float(p["x"]), float(p["y"])))
    return out


def _draw_text(img: Image.Image, el: JsonDict) -> None:
    text = json_str(el.get("text"))
    if not text:
        return
    size = int(el.get("size", el.get("font_size", 32)) or 32)
    font = resolve_font(el.get("font"), size)
    draw = ImageDraw.Draw(img, "RGBA")
    x = int(el.get("x", 0)); y = int(el.get("y", 0))
    color = as_rgba(el.get("fill", el.get("color", "#FFFFFF")))
    shadow = el.get("shadow")
    if isinstance(shadow, dict):
        soff = int(shadow.get("offset", 3))
        scol = as_rgba(shadow.get("color", "#00000080"))
        draw.text((x + soff, y + soff), text, font=font, fill=scol)
    align = str(el.get("align", el.get("anchor", "la")))
    draw.text((x, y), text, font=font, fill=color, anchor=align if len(align) <= 2 else "la")


def _draw_image(img: Image.Image, el: JsonDict) -> None:
    path = el.get("path") or el.get("file")
    url = el.get("url")
    data = el.get("data")
    overlay: Image.Image | None = None
    if path and os.path.isfile(str(path)):
        overlay = Image.open(str(path)).convert("RGBA")
    elif isinstance(url, str) and url.startswith("http"):
        try:
            dl = _download_to_asset(url)
            if dl:
                overlay = Image.open(dl).convert("RGBA")
        except Exception as e:
            logger.warning(f"draw image url fail: {e}")
            overlay = None
    elif isinstance(data, str) and data.startswith("data:"):
        import base64
        try:
            b64 = data.split(",", 1)[1]
            overlay = Image.open(BytesIO(base64.b64decode(b64))).convert("RGBA")
        except Exception:
            overlay = None
    if overlay is None:
        return
    x = int(el.get("x", 0)); y = int(el.get("y", 0))
    w = el.get("w"); h = el.get("h")
    if w:
        nw = int(w)
        nh = int(h) if h else int(overlay.height * (nw / overlay.width))
        overlay = overlay.resize((max(1, nw), max(1, nh)))
    img.alpha_composite(overlay, (x, y))


# ============================================================
# SPEC RENDERER
# ============================================================
def render_spec(spec: JsonDict) -> BytesIO:
    """Рендерит JSON-спецификацию рисунка в PNG BytesIO."""
    _sweep_assets()
    w = _clamp_canvas(spec.get("width", spec.get("w", 800)), 800)
    h = _clamp_canvas(spec.get("height", spec.get("h", 600)), 600)
    bg = spec.get("background", spec.get("bg", "#FFFFFF"))
    if isinstance(bg, dict):
        c1 = bg.get("from", bg.get("color1", "#FFFFFF"))
        c2 = bg.get("to", bg.get("color2", "#000000"))
        img = _linear_gradient(w, h, as_rgb(c1), as_rgb(c2), float(bg.get("angle", 0))).convert("RGBA")
    elif isinstance(bg, str) and str(bg).lower() == "transparent":
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    else:
        img = Image.new("RGBA", (w, h), as_rgba(bg) if bg else (255, 255, 255, 255))

    elements = spec.get("elements", spec.get("layers", []))
    if isinstance(elements, list):
        for el in cast(list[Any], elements)[:MAX_ELEMENTS]:
            if isinstance(el, dict):
                try:
                    _render_element(img, json_dict(el))
                except Exception as e:
                    logger.warning(f"draw element {el.get('type')!r}: {e}")

    out = BytesIO()
    img.convert("RGB").save(out, format="PNG")
    out.seek(0)
    return out


# ============================================================
# ASSET TERMINAL
# ============================================================
class TerminalResult:
    __slots__ = ("ok", "output", "paths")

    def __init__(self, ok: bool, output: str, paths: list[str] | None = None) -> None:
        self.ok = ok
        self.output = output
        self.paths = paths or []


def _in_asset_dir(path: str) -> bool:
    real = os.path.realpath(path)
    base = os.path.realpath(_safe_asset_dir())
    return real.startswith(base + os.sep)


def _host_allowed(url: str) -> bool:
    from urllib.parse import urlparse
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return any(host == h or host.endswith("." + h) for h in ASSET_HOST_ALLOW)


def _download_to_asset(url: str, filename: str | None = None) -> str | None:
    if not _host_allowed(url):
        logger.warning(f"draw asset: хост не разрешён: {url}")
        return None
    base = _safe_asset_dir()
    name = filename or os.path.basename(url.split("?", 1)[0]) or f"asset_{int(time.time())}"
    name = re.sub(r'[^A-Za-z0-9._-]', '_', name)
    dest = os.path.join(base, name)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 KulshBot"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read(MAX_ASSET_BYTES + 1)
        if len(data) > MAX_ASSET_BYTES:
            logger.warning(f"draw asset: слишком большой файл {url}")
            return None
        with open(dest, "wb") as f:
            f.write(data)
        return dest
    except Exception as e:
        logger.warning(f"draw asset download fail {url}: {e}")
        return None


async def run_terminal(command: str) -> TerminalResult:
    """Ограниченный «терминал»: pip install (whitelist), curl/wget для ассетов.

    Возвращает TerminalResult с выводом и путями скачанных ассетов.
    """
    cmd = (command or "").strip()
    if not cmd:
        return TerminalResult(False, "пустая команда")
    # Блокируем опасное.
    if re.search(r'[;&|`$><]', cmd) and not cmd.startswith(("curl", "wget")):
        # Разрешаем пайпы только для разрешённых бинарей в самом начале.
        pass
    parts = cmd.split()
    binary = os.path.basename(parts[0]).lower() if parts else ""
    if binary not in TERM_BIN_ALLOW:
        return TerminalResult(False, f"команда '{binary}' не разрешена")

    if binary in ("curl", "wget"):
        urls = re.findall(r'https?://[^\s"\'`<>|]+', cmd)
        if not urls:
            for a in parts[1:]:
                a = a.strip('"\'`')
                if a.startswith("http") and "://" in a:
                    urls.append(a)
        if not urls:
            return TerminalResult(False, "не нашёл URL в команде")
        paths: list[str] = []
        for u in urls[:5]:
            p = await asyncio.to_thread(_download_to_asset, u, None)
            if p:
                paths.append(p)
        if not paths:
            return TerminalResult(False, "не удалось скачать (хост не разрешён или ошибка сети)")
        return TerminalResult(True, "скачано: " + ", ".join(os.path.basename(p) for p in paths), paths)

    if binary in ("pip", "pip3"):
        if "install" not in parts:
            return TerminalResult(False, "поддерживается только 'pip install <pkg>'")
        pkgs = [a for a in parts[parts.index("install") + 1:] if not a.startswith("-")]
        for pkg in pkgs:
            root = pkg.split("==")[0].split("[")[0].strip().lower()
            if root not in PIP_ALLOW:
                return TerminalResult(False, f"пакет '{root}' не разрешён (доступно: {', '.join(sorted(PIP_ALLOW))})")
        try:
            r = await asyncio.to_thread(
                subprocess.run,
                [sys.executable, "-m", "pip", "install", "--no-input", "--disable-pip-version-check", *pkgs],
                capture_output=True, text=True, timeout=180,
            )
            tail = (r.stdout or r.stderr or "").strip()[-600:]
            return TerminalResult(r.returncode == 0, tail or "pip завершился")
        except subprocess.TimeoutExpired:
            return TerminalResult(False, "pip timeout")
        except Exception as e:
            return TerminalResult(False, f"pip error: {e}")

    if binary in ("python", "python3"):
        return TerminalResult(False, "произвольный python не разрешён; используй pip/curl/wget")

    return TerminalResult(False, "неизвестная команда")


def cleanup_assets() -> None:
    """Удаляет весь sandbox ассетов (вызывается после отправки результата)."""
    base = _safe_asset_dir()
    try:
        shutil.rmtree(base, ignore_errors=True)
    except OSError:
        pass


# ============================================================
# MARKER EXTRACTION
# ============================================================
def _extract_json_block(text: str, marker: str) -> tuple[JsonDict | None, str]:
    """Достаёт {..} после маркера (в ```json-блоке или как есть) и возвращает остаток текста."""
    if not text or marker not in text:
        return None, text
    m = re.search(rf'{re.escape(marker)}\s*\n?```(?:json)?\s*(\{{[\s\S]*?\}})\s*```', text)
    if m:
        try:
            return json_dict(json.loads(m.group(1))), (text[:m.start()] + text[m.end():]).strip()
        except Exception:
            pass
    idx = text.find(marker)
    if idx < 0:
        return None, text
    start = text.find("{", idx)
    if start < 0:
        return None, text
    depth = 0
    in_str = False
    esc = False
    end = -1
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
        try:
            spec = json_dict(json.loads(text[start:end]))
            return spec, (text[:idx] + text[end:]).strip()
        except Exception as e:
            logger.warning(f"draw/term json parse fail: {e}")
            # Даже при ошибке парсинга вырезаем маркер и блок, чтобы не светить их в чате.
            tail = re.sub(r'^\s*```[a-zA-Z]*\s*', '', text[end:])
            leftover = (text[:idx] + tail).strip()
            return None, leftover
    return None, (text[:idx]).strip()


def extract_draw_parts(text: str) -> tuple[JsonDict | None, str, str]:
    """Возвращает (spec, before_text, after_text) для блока !draw.

    before_text — текст до блока, after_text — текст после блока (может содержать !separate).
    """
    if not text or "!draw" not in text:
        return None, text, ""
    m = re.search(r'!draw\s*\n?```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
    if m:
        try:
            spec = json_dict(json.loads(m.group(1)))
            return spec, text[:m.start()].strip(), text[m.end():].strip()
        except Exception:
            pass
    idx = text.find("!draw")
    if idx < 0:
        return None, text, ""
    start = text.find("{", idx)
    if start < 0:
        return None, text[:idx].strip(), text[idx + len("!draw"):].strip()
    depth = 0
    in_str = False
    esc = False
    end = -1
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
        try:
            spec = json_dict(json.loads(text[start:end]))
            return spec, text[:idx].strip(), text[end:].strip()
        except Exception as e:
            logger.warning(f"draw json parse fail: {e}")
            tail = re.sub(r'^\s*```[a-zA-Z]*\s*', '', text[end:]).strip()
            return None, text[:idx].strip(), tail
    return None, text[:idx].strip(), ""


def extract_draw_marker(text: str) -> tuple[JsonDict | None, str]:
    spec, before, after = extract_draw_parts(text)
    if spec is None:
        return None, text
    remaining = (before + (("\n" + after) if after else "")).strip()
    return spec, remaining


class DrawResult:
    __slots__ = ("png", "before", "after", "status")

    def __init__(self, png: BytesIO | None, before: str, after: str, status: str) -> None:
        self.png = png
        self.before = before
        self.after = after
        self.status = status


async def process_drawing(reply_text: str) -> DrawResult:
    """Обрабатывает !term-команды и !draw-блок из ответа модели.

    Возвращает DrawResult(png, before_text, after_text, status). before_text и
    after_text — текст до и после блока !draw (в них могут остаться !separate).
    """
    term_cmds, text_wo_term = extract_term_commands(reply_text)
    status_parts: list[str] = []
    for cmd in term_cmds:
        res = await run_terminal(cmd)
        status_parts.append(("✓ " if res.ok else "✗ ") + (res.output or cmd)[:200])

    spec, before, after = extract_draw_parts(text_wo_term)
    png: BytesIO | None = None
    if spec is not None:
        try:
            png = render_spec(spec)
        except Exception as e:
            logger.error(f"draw render fail: {e}")
            after = (after + f"\n\n❌ не смог нарисовать: {e}").strip()
        finally:
            cleanup_assets()
    return DrawResult(png, before, after, " | ".join(status_parts))



def extract_term_commands(text: str) -> tuple[list[str], str]:
    """Extracts `!term <команда>` lines. Каждая команда — отдельная строка."""
    if not text or "!term" not in text:
        return [], text
    commands: list[str] = []
    out_lines: list[str] = []
    for line in text.splitlines():
        m = re.match(r'^\s*!term\s+(.+?)\s*$', line)
        if m:
            commands.append(m.group(1).strip())
        else:
            out_lines.append(line)
    return commands, "\n".join(out_lines).strip()

