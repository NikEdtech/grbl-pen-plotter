"""Text → single-stroke polylines (stick / Hershey-style font)."""

from __future__ import annotations

from typing import List, Tuple

from grbl_pen_plotter.fonts.stick import ADVANCE, GLYPHS, LINE_EM, _s

Point = Tuple[float, float]
Stroke = List[Point]


def glyph_paths(ch: str) -> List[Stroke]:
    if ch in GLYPHS:
        return GLYPHS[ch]
    if ch.lower() in GLYPHS:
        return GLYPHS[ch.lower()]
    # missing glyph: box
    return _s("1,1 9,1 9,13 1,13 1,1", "1,1 9,13")


def text_to_strokes(
    text: str,
    *,
    origin: Tuple[float, float] = (5.0, 5.0),
    scale: float = 0.45,
    line_spacing: float = 1.15,
    max_width: float | None = None,
    y_down: bool = True,
) -> List[Stroke]:
    """Layout text as strokes in work mm.

    Font em y-up; if y_down=True (SVG/paper convention), invert within glyph.
    origin is top-left of first line when y_down else bottom-left baseline-ish.
    """
    x0, y0 = origin
    x, y = x0, y0
    out: List[Stroke] = []
    if max_width is None:
        max_width = 1e9

    def emit_word(word: str, wx: float, wy: float) -> float:
        for ch in word:
            for stroke in glyph_paths(ch):
                pts: Stroke = []
                for px, py in stroke:
                    if y_down:
                        pts.append((wx + px * scale, wy + (14 - py) * scale))
                    else:
                        pts.append((wx + px * scale, wy + py * scale))
                if len(pts) >= 2:
                    out.append(pts)
            wx += ADVANCE * scale
        return wx

    for paragraph in text.split("\n"):
        words = paragraph.split(" ")
        x = x0
        for i, word in enumerate(words):
            w = len(word) * ADVANCE * scale
            space = ADVANCE * scale * 0.7 if i > 0 else 0.0
            if x > x0 and x + space + w > x0 + max_width:
                y += LINE_EM * scale * line_spacing
                x = x0
                space = 0.0
            x = emit_word(word, x + space, y)
        y += LINE_EM * scale * line_spacing
    return out
