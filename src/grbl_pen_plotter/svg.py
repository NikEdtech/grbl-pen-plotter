"""SVG path/polyline extraction and fit-to-paper transforms."""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

from grbl_pen_plotter.profile import PAPER, PaperSize

Point = Tuple[float, float]
Stroke = List[Point]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _nums(s: str) -> List[float]:
    return [float(x) for x in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", s)]


def cubic(p0, p1, p2, p3, n=16):
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
        pts.append((x, y))
    return pts


def quad(p0, p1, p2, n=12):
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        x = u**2 * p0[0] + 2 * u * t * p1[0] + t**2 * p2[0]
        y = u**2 * p0[1] + 2 * u * t * p1[1] + t**2 * p2[1]
        pts.append((x, y))
    return pts


def parse_path_d(d: str) -> List[Stroke]:
    tokens = re.findall(
        r"[MmLlHhVvCcQqZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?",
        d.replace(",", " "),
    )
    strokes: List[Stroke] = []
    cur: Stroke = []
    x = y = 0.0
    sx = sy = 0.0
    i = 0
    cmd = "M"

    def flush():
        nonlocal cur
        if len(cur) >= 2:
            strokes.append(cur)
        cur = []

    while i < len(tokens):
        t = tokens[i]
        if re.match(r"[A-Za-z]", t):
            cmd = t
            i += 1
            if cmd in "Zz":
                if cur:
                    cur.append((sx, sy))
                    x, y = sx, sy
                flush()
                continue
        else:
            if cmd == "M":
                cmd = "L"
            elif cmd == "m":
                cmd = "l"

        def take(n):
            nonlocal i
            vals = [float(tokens[i + k]) for k in range(n)]
            i += n
            return vals

        abs_cmd = cmd.upper()
        rel = cmd.islower()

        if abs_cmd == "M":
            flush()
            nx, ny = take(2)
            if rel:
                nx += x
                ny += y
            x, y = nx, ny
            sx, sy = x, y
            cur = [(x, y)]
            while i < len(tokens) and not re.match(r"[A-Za-z]", tokens[i]):
                nx, ny = take(2)
                if rel:
                    nx += x
                    ny += y
                x, y = nx, ny
                cur.append((x, y))
        elif abs_cmd == "L":
            while i < len(tokens) and not re.match(r"[A-Za-z]", tokens[i]):
                nx, ny = take(2)
                if rel:
                    nx += x
                    ny += y
                x, y = nx, ny
                cur.append((x, y))
        elif abs_cmd == "H":
            while i < len(tokens) and not re.match(r"[A-Za-z]", tokens[i]):
                nx = take(1)[0]
                if rel:
                    nx += x
                x = nx
                cur.append((x, y))
        elif abs_cmd == "V":
            while i < len(tokens) and not re.match(r"[A-Za-z]", tokens[i]):
                ny = take(1)[0]
                if rel:
                    ny += y
                y = ny
                cur.append((x, y))
        elif abs_cmd == "C":
            while i < len(tokens) and not re.match(r"[A-Za-z]", tokens[i]):
                vals = take(6)
                if rel:
                    c1 = (x + vals[0], y + vals[1])
                    c2 = (x + vals[2], y + vals[3])
                    end = (x + vals[4], y + vals[5])
                else:
                    c1 = (vals[0], vals[1])
                    c2 = (vals[2], vals[3])
                    end = (vals[4], vals[5])
                segs = cubic((x, y), c1, c2, end)
                cur.extend(segs[1:])
                x, y = end
        elif abs_cmd == "Q":
            while i < len(tokens) and not re.match(r"[A-Za-z]", tokens[i]):
                vals = take(4)
                if rel:
                    c1 = (x + vals[0], y + vals[1])
                    end = (x + vals[2], y + vals[3])
                else:
                    c1 = (vals[0], vals[1])
                    end = (vals[2], vals[3])
                segs = quad((x, y), c1, end)
                cur.extend(segs[1:])
                x, y = end
        else:
            if i < len(tokens) and not re.match(r"[A-Za-z]", tokens[i]):
                i += 1
            else:
                break

    flush()
    return strokes


def extract_strokes(svg: Union[str, Path]) -> List[Stroke]:
    if isinstance(svg, Path) or (isinstance(svg, str) and Path(svg).is_file()):
        tree = ET.parse(str(svg))
        root = tree.getroot()
    else:
        root = ET.fromstring(svg)

    strokes: List[Stroke] = []
    for el in root.iter():
        tag = _local(el.tag)
        if tag in {"polyline", "polygon"}:
            pts = _nums(el.get("points", ""))
            pl = [(pts[i], pts[i + 1]) for i in range(0, len(pts) - 1, 2)]
            if tag == "polygon" and pl and pl[0] != pl[-1]:
                pl.append(pl[0])
            if len(pl) >= 2:
                strokes.append(pl)
        elif tag == "line":
            strokes.append(
                [
                    (float(el.get("x1", 0)), float(el.get("y1", 0))),
                    (float(el.get("x2", 0)), float(el.get("y2", 0))),
                ]
            )
        elif tag == "path":
            d = el.get("d", "")
            if d:
                strokes.extend(parse_path_d(d))
        elif tag == "circle":
            cx, cy, r = float(el.get("cx", 0)), float(el.get("cy", 0)), float(el.get("r", 0))
            n = 48
            strokes.append(
                [
                    (cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
                    for i in range(n + 1)
                ]
            )
        elif tag == "rect":
            x, y = float(el.get("x", 0)), float(el.get("y", 0))
            w, h = float(el.get("width", 0)), float(el.get("height", 0))
            strokes.append([(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)])
    return strokes


def bounds(strokes: Sequence[Stroke]) -> Tuple[float, float, float, float]:
    xs = [p[0] for s in strokes for p in s]
    ys = [p[1] for s in strokes for p in s]
    return min(xs), min(ys), max(xs), max(ys)


def fit_strokes(
    strokes: Sequence[Stroke],
    *,
    paper: Union[str, PaperSize] = "A4",
    margin_mm: float = 10.0,
    target_width: Optional[float] = None,
    target_height: Optional[float] = None,
    origin: Tuple[float, float] = (0.0, 0.0),
    flip_y: bool = True,
    scale: Optional[float] = None,
) -> Tuple[List[Stroke], float]:
    """Scale/fit strokes into a paper rectangle (work mm, origin at bottom-left-ish)."""
    if isinstance(paper, str):
        paper = PAPER[paper.upper()]
    minx, miny, maxx, maxy = bounds(strokes)
    w = max(maxx - minx, 1e-9)
    h = max(maxy - miny, 1e-9)

    usable_w = (target_width if target_width is not None else paper.width_mm) - 2 * margin_mm
    usable_h = (target_height if target_height is not None else paper.height_mm) - 2 * margin_mm
    if usable_w <= 0 or usable_h <= 0:
        raise ValueError("Paper/margins leave no usable area")

    if scale is None:
        scale = min(usable_w / w, usable_h / h)

    dw = usable_w - w * scale
    dh = usable_h - h * scale
    ox = origin[0] + margin_mm + dw / 2
    oy = origin[1] + margin_mm + dh / 2

    out: List[Stroke] = []
    for s in strokes:
        ns: Stroke = []
        for x, y in s:
            nx = ox + (x - minx) * scale
            if flip_y:
                ny = oy + (maxy - y) * scale
            else:
                ny = oy + (y - miny) * scale
            ns.append((nx, ny))
        out.append(ns)
    return out, scale
