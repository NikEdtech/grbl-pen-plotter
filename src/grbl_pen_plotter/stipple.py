"""Experimental weighted stipple → G-code (NN + light 2-opt).

Quality varies by image and paper; marked experimental because dense hops can
look like worms rather than clean dots if lift thresholds are wrong.
"""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageOps

Point = Tuple[float, float]
Stroke = List[Point]


def sample_stipple(
    image: Image.Image,
    max_points: int = 2000,
    *,
    seed: int = 1,
    invert: bool = False,
    gamma: float = 1.4,
) -> List[Point]:
    gray = ImageOps.grayscale(image)
    w, h = gray.size
    px = gray.load()
    rng = random.Random(seed)
    weights: List[float] = []
    coords: List[Tuple[int, int]] = []
    step = max(1, int(math.sqrt((w * h) / (max_points * 8))))
    for y in range(0, h, step):
        for x in range(0, w, step):
            v = px[x, y]
            if invert:
                v = 255 - v
            darkness = (255 - v) / 255.0
            weight = darkness**gamma
            if weight <= 1e-6:
                continue
            weights.append(weight)
            coords.append((x, y))
    if not weights:
        return []
    total = sum(weights)
    cdf: List[float] = []
    acc = 0.0
    for wt in weights:
        acc += wt / total
        cdf.append(acc)
    pts: List[Point] = []
    for _ in range(max_points):
        r = rng.random()
        lo, hi = 0, len(cdf) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if cdf[mid] < r:
                lo = mid + 1
            else:
                hi = mid
        x, y = coords[lo]
        # jitter within cell
        pts.append((x + rng.random() * step, y + rng.random() * step))
    return pts


def nearest_neighbor_order(points: Sequence[Point]) -> List[Point]:
    if not points:
        return []
    remaining = list(points)
    ordered = [remaining.pop(0)]
    while remaining:
        cx, cy = ordered[-1]
        best_i = 0
        best_d = 1e18
        for i, (x, y) in enumerate(remaining):
            d = (x - cx) ** 2 + (y - cy) ** 2
            if d < best_d:
                best_d = d
                best_i = i
        ordered.append(remaining.pop(best_i))
    return ordered


def two_opt(points: List[Point], rounds: int = 2) -> List[Point]:
    if len(points) < 4:
        return points
    path = points[:]
    n = len(path)
    for _ in range(rounds):
        improved = False
        for i in range(1, n - 2):
            for j in range(i + 1, n):
                if j - i == 1:
                    continue
                a, b = path[i - 1], path[i]
                c, d = path[j - 1], path[j % n]
                before = math.hypot(a[0] - b[0], a[1] - b[1]) + math.hypot(c[0] - d[0], c[1] - d[1])
                after = math.hypot(a[0] - c[0], a[1] - c[1]) + math.hypot(b[0] - d[0], b[1] - d[1])
                if after + 1e-9 < before:
                    path[i:j] = reversed(path[i:j])
                    improved = True
        if not improved:
            break
    return path


def points_to_dot_strokes(
    points: Sequence[Point],
    *,
    tick_mm: float = 0.35,
    lift_threshold: float = 3.0,
) -> List[Stroke]:
    """Short dashes; connect hops under lift_threshold without a new stroke."""
    if not points:
        return []
    strokes: List[Stroke] = []
    cur: Stroke = []
    prev: Optional[Point] = None
    for x, y in points:
        if prev is None:
            cur = [(x, y), (x + tick_mm, y)]
        else:
            dist = math.hypot(x - prev[0], y - prev[1])
            if dist <= lift_threshold and cur:
                cur.append((x, y))
                cur.append((x + tick_mm, y))
            else:
                if len(cur) >= 2:
                    strokes.append(cur)
                cur = [(x, y), (x + tick_mm, y)]
        prev = (x, y)
    if len(cur) >= 2:
        strokes.append(cur)
    return strokes


def image_to_stipple_strokes(
    path: Path,
    *,
    max_points: int = 2000,
    width_mm: float = 90.0,
    height_mm: float = 90.0,
    origin: Tuple[float, float] = (5.0, 5.0),
    seed: int = 1,
    lift_threshold: float = 3.0,
) -> List[Stroke]:
    im = Image.open(path).convert("RGB")
    pts = sample_stipple(im, max_points=max_points, seed=seed)
    pts = nearest_neighbor_order(pts)
    pts = two_opt(pts, rounds=2)
    if not pts:
        return []
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    bw = max(maxx - minx, 1e-9)
    bh = max(maxy - miny, 1e-9)
    scale = min(width_mm / bw, height_mm / bh)
    mapped = [
        (origin[0] + (x - minx) * scale, origin[1] + (y - miny) * scale) for x, y in pts
    ]
    return points_to_dot_strokes(mapped, lift_threshold=lift_threshold)
