"""Emit GRBL pen G-code from stroke lists."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Sequence, Tuple

from grbl_pen_plotter.bounds import BoundsReport, check_strokes
from grbl_pen_plotter.profile import Profile

Point = Tuple[float, float]
Stroke = List[Point]


def emit_strokes(
    strokes: Sequence[Stroke],
    profile: Profile,
    *,
    source: str = "",
    flip_x: bool = False,
    flip_y: bool = False,
    validate: bool = True,
    g92_machine: Optional[Tuple[float, float]] = None,
) -> Tuple[str, BoundsReport]:
    """Convert strokes (work mm) to G-code. Optionally flip for paper orientation."""
    prepared: List[Stroke] = []
    # Determine bounds for flip
    from grbl_pen_plotter.bounds import stroke_bounds

    if strokes and any(strokes):
        minx, miny, maxx, maxy = stroke_bounds(strokes)
    else:
        minx = miny = maxx = maxy = 0.0

    for s in strokes:
        if len(s) < 2:
            continue
        ns: Stroke = []
        for x, y in s:
            nx = (maxx + minx - x) if flip_x else x
            ny = (maxy + miny - y) if flip_y else y
            ns.append((nx, ny))
        prepared.append(ns)

    report = check_strokes(prepared, profile.limits, g92_machine=g92_machine)
    if validate and not report.ok:
        raise ValueError(f"Bounds check failed: {report.message}; sample={report.out_sample}")

    pen = profile.pen
    feeds = profile.feeds
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    wb = report.work_bbox
    lines = [
        f"; grbl-pen-plotter — {profile.name}",
        f"; source: {source}",
        f"; generated: {now}",
        f"; work bbox: X{wb[0]:.2f}..{wb[2]:.2f} Y{wb[1]:.2f}..{wb[3]:.2f}",
        f"; path ≈ {report.path_length_mm:.0f} mm",
        f"; pen: {pen.spindle_on} + G0 Z{pen.z_down} down; G0 Z{pen.z_up} + {pen.spindle_off} up",
        f"; set $1={profile.grbl.step_idle_plotting} while plotting; cool with $1={profile.grbl.step_idle_cool}",
        f"; keep $32={profile.grbl.laser_mode} (laser mode OFF for pens)",
        "G21",
        "G90",
        "G94",
        pen.spindle_off,
        f"G0 Z{pen.z_up:.3f}",
    ]
    for s in prepared:
        x0, y0 = s[0]
        lines.append(f"G0 X{x0:.3f} Y{y0:.3f} F{feeds.rapid:.0f}")
        if pen.hold_spindle_during_stroke:
            lines.append(pen.spindle_on)
        lines.append(f"G0 Z{pen.z_down:.3f} F{pen.z_feed:.0f}")
        for x, y in s[1:]:
            lines.append(f"G1 X{x:.3f} Y{y:.3f} F{feeds.draw:.0f}")
        lines.append(f"G0 Z{pen.z_up:.3f} F{pen.z_feed:.0f}")
        lines.append(pen.spindle_off)
    lines.append(pen.spindle_off)
    lines.append(f"G0 Z{pen.z_up:.3f}")
    lines.append(f"G0 X0 Y0 F{feeds.rapid:.0f}")
    lines.append("S0")
    return "\n".join(lines) + "\n", report


def square_strokes(side_mm: float = 50.0, origin: Tuple[float, float] = (5.0, 5.0)) -> List[Stroke]:
    ox, oy = origin
    s = side_mm
    return [[(ox, oy), (ox + s, oy), (ox + s, oy + s), (ox, oy + s), (ox, oy)]]
