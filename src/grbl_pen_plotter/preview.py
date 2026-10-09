"""Dry-run preview: render toolpaths to SVG / PNG."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

from grbl_pen_plotter.bounds import parse_gcode_xy, stroke_bounds

Point = Tuple[float, float]
Stroke = List[Point]


def strokes_to_svg(
    strokes: Sequence[Stroke],
    *,
    width_mm: Optional[float] = None,
    height_mm: Optional[float] = None,
    margin: float = 5.0,
    stroke_width: float = 0.35,
) -> str:
    if not strokes or not any(strokes):
        return (
            '<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" '
            'width="100mm" height="100mm"/>'
        )
    minx, miny, maxx, maxy = stroke_bounds(strokes)
    w = (width_mm if width_mm is not None else (maxx - minx + 2 * margin))
    h = (height_mm if height_mm is not None else (maxy - miny + 2 * margin))
    # shift into view with margin
    ox = margin - minx
    oy = margin - miny
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.2f}mm" height="{h:.2f}mm" '
        f'viewBox="0 0 {w:.2f} {h:.2f}">',
        f'  <rect x="0" y="0" width="{w:.2f}" height="{h:.2f}" fill="#fafafa"/>',
    ]
    for s in strokes:
        if len(s) < 2:
            continue
        d = [f"M {s[0][0]+ox:.3f},{s[0][1]+oy:.3f}"]
        for x, y in s[1:]:
            d.append(f"L {x+ox:.3f},{y+oy:.3f}")
        parts.append(
            f'  <path d="{" ".join(d)}" fill="none" stroke="#111" '
            f'stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def gcode_to_strokes(text: str) -> List[Stroke]:
    """Approximate draw strokes from G-code (pen-down segments)."""
    strokes: List[Stroke] = []
    cur: Stroke = []
    pen_down = False
    x = y = 0.0
    for raw in text.splitlines():
        line = raw.split(";")[0].strip()
        if not line:
            continue
        upper = line.upper()
        # pen heuristics
        zm = re.search(r"Z\s*(-?\d+(?:\.\d*)?)", upper)
        if zm:
            z = float(zm.group(1))
            # assume z_up ≈ 0, z_down > 0 (JinGan polarity)
            if "G0" in upper or "G00" in upper or "G1" in upper or "G01" in upper:
                if z > 0.5:
                    pen_down = True
                elif z <= 0.5:
                    if cur and len(cur) >= 2:
                        strokes.append(cur)
                    cur = []
                    pen_down = False
        if upper.startswith("M5"):
            if cur and len(cur) >= 2:
                strokes.append(cur)
            cur = []
            pen_down = False
        if not (upper.startswith("G0") or upper.startswith("G00") or upper.startswith("G1") or upper.startswith("G01")):
            continue
        nx, ny = x, y
        for axis, val in re.findall(r"([XY])\s*(-?\d+(?:\.\d*)?)", upper):
            if axis == "X":
                nx = float(val)
            else:
                ny = float(val)
        if (nx, ny) == (x, y) and "X" not in upper and "Y" not in upper:
            continue
        # travel vs draw
        is_rapid = upper.startswith("G0")
        if pen_down and not is_rapid:
            if not cur:
                cur = [(x, y)]
            cur.append((nx, ny))
        elif pen_down and is_rapid and "Z" not in upper:
            # rare
            if not cur:
                cur = [(x, y)]
            cur.append((nx, ny))
        else:
            if cur and len(cur) >= 2:
                strokes.append(cur)
            cur = []
        x, y = nx, ny
    if cur and len(cur) >= 2:
        strokes.append(cur)
    # fallback: all XY as one polyline
    if not strokes:
        pts = parse_gcode_xy(text.splitlines())
        if len(pts) >= 2:
            strokes = [pts]
    return strokes


def render_preview(
    strokes: Sequence[Stroke],
    out: Union[str, Path],
    *,
    png_scale: float = 8.0,
) -> Path:
    """Write SVG and optionally PNG (by extension)."""
    out = Path(out)
    svg = strokes_to_svg(strokes)
    if out.suffix.lower() == ".png":
        svg_path = out.with_suffix(".svg")
        svg_path.write_text(svg, encoding="utf-8")
        _svg_to_png(svg, out, scale=png_scale)
        return out
    out.write_text(svg, encoding="utf-8")
    return out


def _svg_to_png(svg: str, out: Path, scale: float = 8.0) -> None:
    from PIL import Image, ImageDraw

    # Simple rasterizer without cairo: parse paths roughly
    strokes = []
    for m in re.finditer(r'd="([^"]+)"', svg):
        d = m.group(1)
        pts: Stroke = []
        for tok in re.finditer(r"([ML])\s*([-\d.]+),([-\d.]+)", d):
            pts.append((float(tok.group(2)), float(tok.group(3))))
        if len(pts) >= 2:
            strokes.append(pts)
    if not strokes:
        Image.new("RGB", (200, 200), "white").save(out)
        return
    minx, miny, maxx, maxy = stroke_bounds(strokes)
    pad = 4.0
    w = max(int((maxx - minx + 2 * pad) * scale), 32)
    h = max(int((maxy - miny + 2 * pad) * scale), 32)
    im = Image.new("RGB", (w, h), (250, 250, 250))
    draw = ImageDraw.Draw(im)

    def tx(x, y):
        return (
            (x - minx + pad) * scale,
            (y - miny + pad) * scale,
        )

    for s in strokes:
        xy = [tx(x, y) for x, y in s]
        draw.line(xy, fill=(20, 20, 20), width=max(1, int(scale * 0.12)))
    im.save(out)
