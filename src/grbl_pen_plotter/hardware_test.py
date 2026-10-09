"""Safe hardware smoke tests for a connected JinGan-class plotter."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from grbl_pen_plotter.gcode import emit_strokes, square_strokes
from grbl_pen_plotter.grbl import AlarmError, Grbl, GrblError, make_logger
from grbl_pen_plotter.ports import autodetect_port, list_ports
from grbl_pen_plotter.preview import gcode_to_strokes, render_preview
from grbl_pen_plotter.profile import Profile
from grbl_pen_plotter.stream import stream_file
from grbl_pen_plotter.text import text_to_strokes


def plotter_connected(hint: str = "usbserial") -> Optional[str]:
    return autodetect_port(hint)


def run_hardware_test(
    profile: Profile,
    *,
    port: Optional[str] = None,
    skip_plot: bool = False,
    verbose: bool = True,
    artifact_dir: Optional[Path] = None,
) -> int:
    """Status → small jog → pen cycle → optional 5 cm square + «Test Тест».

    Stops immediately on alarm. Drawing stays within ~60×60 mm from current origin.
    """
    port = port or plotter_connected(profile.default_port_hint)
    if not port:
        print("Plotter not connected (no /dev/cu.usbserial* or similar).")
        print("See docs/HARDWARE_TEST.md for the manual checklist.")
        ports = list_ports()
        if ports:
            print("Available ports:")
            for p in ports:
                print(f"  {p['device']}  {p['description']}")
        return 2

    log = make_logger() if verbose else (lambda k, m: None)
    artifact_dir = artifact_dir or Path("artifacts/hwtest")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    print(f"Hardware test on {port}")
    g = Grbl(port, profile.grbl.baud, log=log)
    try:
        g.connect(soft_reset=True)
        g.unlock()

        st = g.status()
        if not st:
            print("FAIL: no status", file=sys.stderr)
            return 1
        print(f"1) status OK: {st.state} ({st.x:.2f},{st.y:.2f},{st.z:.2f})")

        # Small jog + return
        g.jog("X", 1.0, feed=800, profile=profile)
        g.wait_idle(timeout=30)
        g.jog("X", -1.0, feed=800, profile=profile)
        g.wait_idle(timeout=30)
        print("2) jog ±1 mm X OK")

        g.ensure_plotting_hold(profile)
        g.pen_down(profile)
        g.wait_idle(timeout=20)
        g.pen_up(profile)
        g.wait_idle(timeout=20)
        print("3) pen down/up cycle OK")

        if skip_plot:
            print("4) plot skipped (--skip-plot)")
            return 0

        print("4) plotting 50 mm square + «Test Тест» within 60×60 mm…")
        print("   Ensure paper is under the pen and origin is set (corner, pen raised).")
        sq = square_strokes(50.0, origin=(5.0, 5.0))
        txt = text_to_strokes("Test Тест", origin=(5.0, 58.0), scale=0.35, max_width=55.0)
        # Keep text inside 60 mm box: move text below square carefully
        # Use text at y=5 area to the right instead — simpler: below square at y=56 may exceed 60
        # Re-layout: square 5..55, text at y=5 with smaller — place text at (5, 56) with scale that fits height
        # 60 mm box: y from 5 to 65 would exceed — clamp text under square inside 6cm:
        txt = text_to_strokes("Test Тест", origin=(5.0, 56.0), scale=0.28, max_width=55.0)
        strokes = sq + txt
        # Temporary work limits for this small job (restore after)
        lim = profile.limits
        saved = (lim.x_min, lim.x_max, lim.y_min, lim.y_max, lim.margin)
        lim.x_min, lim.x_max, lim.y_min, lim.y_max, lim.margin = 0.0, 70.0, 0.0, 70.0, 2.0
        try:
            gcode, report = emit_strokes(strokes, profile, source="hwtest", validate=True)
        finally:
            lim.x_min, lim.x_max, lim.y_min, lim.y_max, lim.margin = saved

        gcode_path = artifact_dir / "hwtest.gcode"
        gcode_path.write_text(gcode, encoding="utf-8")
        preview_path = artifact_dir / "hwtest_preview.png"
        render_preview(gcode_to_strokes(gcode), preview_path)
        print(f"   gcode: {gcode_path}")
        print(f"   preview: {preview_path} ({report.path_length_mm:.0f} mm path)")

        result = stream_file(g, gcode, profile=profile)
        if not result.ok:
            print(f"FAIL during plot: {result.error}", file=sys.stderr)
            return 1
        g.pen_up(profile)
        g.cool_motors(profile)
        print("4) plot COMPLETE — cool $1 applied")
        print("Hardware test PASSED")
        return 0
    except AlarmError as exc:
        print(f"ALARM — stopped: {exc}", file=sys.stderr)
        try:
            g.abort_safe(profile)
        except Exception:
            pass
        return 1
    except GrblError as exc:
        print(f"GRBL error: {exc}", file=sys.stderr)
        return 1
    finally:
        g.close()
