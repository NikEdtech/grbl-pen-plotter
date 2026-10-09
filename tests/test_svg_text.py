from pathlib import Path

from grbl_pen_plotter.bounds import check_strokes
from grbl_pen_plotter.gcode import emit_strokes, square_strokes
from grbl_pen_plotter.preview import gcode_to_strokes, strokes_to_svg
from grbl_pen_plotter.profile import resolve_profile
from grbl_pen_plotter.svg import extract_strokes, fit_strokes
from grbl_pen_plotter.text import text_to_strokes


def test_square_and_bounds():
    profile = resolve_profile("jingan")
    strokes = square_strokes(50, origin=(10, 10))
    report = check_strokes(strokes, profile.limits)
    assert report.ok
    gcode, report2 = emit_strokes(strokes, profile, source="square")
    assert "G1" in gcode
    assert "M3" in gcode
    assert report2.ok


def test_text_cyrillic():
    strokes = text_to_strokes("Test Тест", origin=(5, 5), scale=0.4, max_width=100)
    assert len(strokes) >= 4
    profile = resolve_profile("jingan")
    gcode, report = emit_strokes(strokes, profile, source="text")
    assert report.ok
    assert "G1" in gcode


def test_svg_fit(tmp_path: Path):
    svg = tmp_path / "box.svg"
    svg.write_text(
        """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <rect x="10" y="10" width="80" height="80"/>
  <path d="M 20 20 L 80 20 L 80 80 L 20 80 Z"/>
</svg>
""",
        encoding="utf-8",
    )
    strokes = extract_strokes(svg)
    assert len(strokes) >= 1
    fitted, scale = fit_strokes(strokes, paper="A5", margin_mm=8)
    assert scale > 0
    profile = resolve_profile("jingan")
    gcode, report = emit_strokes(fitted, profile, source=str(svg))
    assert report.ok
    preview = strokes_to_svg(gcode_to_strokes(gcode))
    assert "<path" in preview


def test_preview_png(tmp_path: Path):
    from grbl_pen_plotter.preview import render_preview

    strokes = square_strokes(20, origin=(0, 0))
    out = tmp_path / "p.png"
    render_preview(strokes, out)
    assert out.is_file()
    assert out.stat().st_size > 50
