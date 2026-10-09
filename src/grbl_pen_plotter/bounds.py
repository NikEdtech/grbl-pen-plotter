"""Toolpath bounds checking against soft workspace limits."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from grbl_pen_plotter.profile import SoftLimits

Point = Tuple[float, float]
Stroke = List[Point]


@dataclass
class BoundsReport:
    ok: bool
    work_bbox: Tuple[float, float, float, float]  # minx,miny,maxx,maxy
    machine_bbox: Optional[Tuple[float, float, float, float]]
    n_points: int
    n_out: int
    out_sample: List[Tuple[float, float]]
    path_length_mm: float
    message: str


def stroke_bounds(strokes: Sequence[Stroke]) -> Tuple[float, float, float, float]:
    xs = [p[0] for s in strokes for p in s]
    ys = [p[1] for s in strokes for p in s]
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


def path_length(strokes: Sequence[Stroke]) -> float:
    dist = 0.0
    for s in strokes:
        for i in range(1, len(s)):
            dist += math.hypot(s[i][0] - s[i - 1][0], s[i][1] - s[i - 1][1])
    return dist


def check_strokes(
    strokes: Sequence[Stroke],
    limits: SoftLimits,
    *,
    g92_machine: Optional[Tuple[float, float]] = None,
) -> BoundsReport:
    """Validate work-space strokes. If g92_machine is set, also check machine XY."""
    if not strokes or not any(strokes):
        return BoundsReport(
            ok=False,
            work_bbox=(0, 0, 0, 0),
            machine_bbox=None,
            n_points=0,
            n_out=0,
            out_sample=[],
            path_length_mm=0.0,
            message="No points in toolpath",
        )

    wb = stroke_bounds(strokes)
    margin = limits.margin
    out: List[Tuple[float, float]] = []
    n = 0
    for s in strokes:
        for x, y in s:
            n += 1
            if not (
                limits.x_min + margin <= x <= limits.x_max - margin
                and limits.y_min + margin <= y <= limits.y_max - margin
            ):
                out.append((x, y))

    machine_bbox = None
    if g92_machine is not None:
        gx, gy = g92_machine
        mxs, mys = [], []
        mx_min = limits.machine_x_min if limits.machine_x_min is not None else limits.x_min
        mx_max = limits.machine_x_max if limits.machine_x_max is not None else limits.x_max
        my_min = limits.machine_y_min if limits.machine_y_min is not None else limits.y_min
        my_max = limits.machine_y_max if limits.machine_y_max is not None else limits.y_max
        out = []
        for s in strokes:
            for x, y in s:
                mx, my = gx + x, gy + y
                mxs.append(mx)
                mys.append(my)
                if not (
                    mx_min + margin <= mx <= mx_max - margin
                    and my_min + margin <= my <= my_max - margin
                ):
                    out.append((mx, my))
        machine_bbox = (min(mxs), min(mys), max(mxs), max(mys))

    ok = len(out) == 0
    msg = "OK — all points inside soft limits" if ok else f"{len(out)} point(s) outside soft limits"
    return BoundsReport(
        ok=ok,
        work_bbox=wb,
        machine_bbox=machine_bbox,
        n_points=n,
        n_out=len(out),
        out_sample=out[:8],
        path_length_mm=path_length(strokes),
        message=msg,
    )


_XY = re.compile(r"([XY])\s*(-?\d+(?:\.\d*)?)", re.I)


def parse_gcode_xy(lines: Iterable[str]) -> List[Point]:
    """Extract absolute XY positions from simple G0/G1 lines (G90 assumed)."""
    x = y = 0.0
    pts: List[Point] = []
    for raw in lines:
        line = raw.split(";")[0].strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("G91") or upper.startswith("$J"):
            # relative / jog — skip for bounds of file streams
            continue
        if not (upper.startswith("G0") or upper.startswith("G00") or upper.startswith("G1") or upper.startswith("G01")):
            # still update XY if present on other moves
            pass
        nx, ny = x, y
        for axis, val in _XY.findall(line):
            if axis.upper() == "X":
                nx = float(val)
            else:
                ny = float(val)
        if (nx, ny) != (x, y) or ("X" in upper or "Y" in upper):
            x, y = nx, ny
            pts.append((x, y))
    return pts


def check_gcode_file(
    text: str,
    limits: SoftLimits,
    *,
    g92_machine: Optional[Tuple[float, float]] = None,
) -> BoundsReport:
    pts = parse_gcode_xy(text.splitlines())
    strokes = [pts] if pts else []
    return check_strokes(strokes, limits, g92_machine=g92_machine)
