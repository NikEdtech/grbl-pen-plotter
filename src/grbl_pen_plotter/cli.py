"""penplot — CLI for GRBL pen plotters."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from grbl_pen_plotter import __version__
from grbl_pen_plotter.bounds import check_gcode_file
from grbl_pen_plotter.gcode import emit_strokes
from grbl_pen_plotter.grbl import Grbl, GrblError, make_logger
from grbl_pen_plotter.ports import autodetect_port, list_ports
from grbl_pen_plotter.preview import gcode_to_strokes, render_preview
from grbl_pen_plotter.profile import resolve_profile
from grbl_pen_plotter.stream import stream_file
from grbl_pen_plotter.svg import extract_strokes, fit_strokes
from grbl_pen_plotter.text import text_to_strokes


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--profile",
        default="jingan",
        help="Profile name or path to TOML (default: jingan)",
    )
    p.add_argument("--port", default=None, help="Serial port (default: autodetect)")
    p.add_argument("-v", "--verbose", action="store_true")


def _port(args, profile) -> str:
    if args.port:
        return args.port
    found = autodetect_port(profile.default_port_hint)
    if not found:
        raise SystemExit(
            "No serial port found. Plug in the plotter (CH340) or pass --port /dev/cu.usbserial-*"
        )
    return found


def _connect(args, profile) -> Grbl:
    port = _port(args, profile)
    log = make_logger() if args.verbose else (lambda k, m: None)
    g = Grbl(port, profile.grbl.baud, log=log)
    g.connect(soft_reset=profile.grbl.soft_reset_on_connect)
    g.unlock()
    return g


def cmd_ports(_args) -> int:
    ports = list_ports()
    if not ports:
        print("No serial ports found.")
        return 1
    auto = autodetect_port()
    for p in ports:
        mark = " *" if p["device"] == auto else ""
        print(f"{p['device']}{mark}\t{p['description']}\t{p['hwid']}")
    if auto:
        print(f"\nAutodetect: {auto}")
    return 0


def cmd_status(args) -> int:
    profile = resolve_profile(args.profile)
    with _connect(args, profile) as g:
        st = g.status()
        if not st:
            print("No status response from GRBL", file=sys.stderr)
            return 1
        kind = "WPos" if st.wpos else "MPos"
        print(f"state={st.state} {kind}=({st.x:.3f},{st.y:.3f},{st.z:.3f})")
        print(st.raw)
    return 0


def cmd_jog(args) -> int:
    profile = resolve_profile(args.profile)
    with _connect(args, profile) as g:
        g.jog(args.axis, args.distance, feed=args.feed, profile=profile)
        g.wait_idle(timeout=60)
        st = g.status()
        if st:
            print(f"OK {st.state} ({st.x:.3f},{st.y:.3f},{st.z:.3f})")
    return 0


def cmd_zero(args) -> int:
    profile = resolve_profile(args.profile)
    with _connect(args, profile) as g:
        # Raise pen first for safety
        g.pen_up(profile)
        g.set_work_zero()
        st = g.status()
        print("Work zero set (G92 X0 Y0 Z0) at current pose — keep pen at max height.")
        if st:
            print(f"status {st.state} ({st.x:.3f},{st.y:.3f},{st.z:.3f})")
    return 0


def cmd_pen(args) -> int:
    profile = resolve_profile(args.profile)
    with _connect(args, profile) as g:
        if args.action == "up":
            g.pen_up(profile)
        else:
            g.ensure_plotting_hold(profile)
            g.pen_down(profile)
        st = g.status()
        if st:
            print(f"pen {args.action}: {st.state} Z≈{st.z:.3f}")
    return 0


def cmd_svg(args) -> int:
    profile = resolve_profile(args.profile)
    strokes = extract_strokes(args.svg)
    if not strokes:
        raise SystemExit(f"No strokes in {args.svg}")
    fitted, scale = fit_strokes(
        strokes,
        paper=args.paper,
        margin_mm=args.margin,
        target_width=args.width,
        target_height=args.height,
        origin=(args.ox, args.oy),
        flip_y=not args.no_flip_y,
        scale=args.scale,
    )
    gcode, report = emit_strokes(
        fitted,
        profile,
        source=str(args.svg),
        flip_x=args.flip_x,
        flip_y=False,  # already handled in fit
        validate=not args.no_bounds_check,
        g92_machine=(args.g92x, args.g92y) if args.g92x is not None else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(gcode, encoding="utf-8")
    print(f"Wrote {args.output} ({len(gcode.splitlines())} lines) scale={scale:.4f}")
    print(report.message, f"path≈{report.path_length_mm:.0f} mm")
    if args.preview:
        prev_strokes = gcode_to_strokes(gcode)
        render_preview(prev_strokes, args.preview)
        print(f"Preview: {args.preview}")
    return 0


def cmd_text(args) -> int:
    profile = resolve_profile(args.profile)
    text = args.text
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    strokes = text_to_strokes(
        text,
        origin=(args.ox, args.oy),
        scale=args.em,
        max_width=args.max_width,
    )
    gcode, report = emit_strokes(
        strokes,
        profile,
        source="text",
        flip_x=args.flip_x,
        flip_y=args.flip_y,
        validate=not args.no_bounds_check,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(gcode, encoding="utf-8")
    print(f"Wrote {args.output} ({len(gcode.splitlines())} lines)")
    print(report.message)
    if args.preview:
        render_preview(gcode_to_strokes(gcode), args.preview)
        print(f"Preview: {args.preview}")
    return 0


def cmd_preview(args) -> int:
    text = Path(args.gcode).read_text(encoding="utf-8")
    strokes = gcode_to_strokes(text)
    out = render_preview(strokes, args.output)
    print(f"Wrote {out} ({len(strokes)} strokes)")
    return 0


def cmd_check(args) -> int:
    profile = resolve_profile(args.profile)
    text = Path(args.gcode).read_text(encoding="utf-8")
    g92 = (args.g92x, args.g92y) if args.g92x is not None else None
    report = check_gcode_file(text, profile.limits, g92_machine=g92)
    print(report.message)
    print(f"work bbox: {report.work_bbox}")
    if report.machine_bbox:
        print(f"machine bbox: {report.machine_bbox}")
    print(f"points={report.n_points} out={report.n_out} path≈{report.path_length_mm:.0f} mm")
    if report.out_sample:
        print(f"out sample: {report.out_sample}")
    return 0 if report.ok else 2


def cmd_stream(args) -> int:
    profile = resolve_profile(args.profile)
    text = Path(args.gcode).read_text(encoding="utf-8")
    report = check_gcode_file(text, profile.limits)
    if not args.no_bounds_check and not report.ok:
        print(f"Bounds check failed: {report.message}", file=sys.stderr)
        print(f"sample: {report.out_sample}", file=sys.stderr)
        return 2
    if args.dry_run:
        print(f"Dry-run OK: {len(text.splitlines())} lines, path≈{report.path_length_mm:.0f} mm")
        if args.preview:
            render_preview(gcode_to_strokes(text), args.preview)
            print(f"Preview: {args.preview}")
        return 0

    log = make_logger()
    port = _port(args, profile)
    g = Grbl(port, profile.grbl.baud, log=log)
    try:
        g.connect(soft_reset=True)
        g.unlock()
        g.ensure_plotting_hold(profile)
        if args.set_zero:
            g.pen_up(profile)
            g.set_work_zero()
        def progress(i, total, cmd):
            if i % 25 == 0 or i == total:
                print(f"… {i}/{total}")

        result = stream_file(g, text, profile=profile, on_progress=progress)
        if result.ok:
            print(f"Complete: {result.lines_sent}/{result.total} lines")
            if args.cool:
                g.cool_motors(profile)
                print(f"Motors cooling ($1={profile.grbl.step_idle_cool})")
            return 0
        print(f"FAILED: {result.error}", file=sys.stderr)
        return 1
    finally:
        g.close()


def cmd_stipple(args) -> int:
    from grbl_pen_plotter.stipple import image_to_stipple_strokes

    print(
        "WARNING: stipple mode is experimental — results may look like worms "
        "instead of clean dots. Tune --lift-threshold and z_down.",
        file=sys.stderr,
    )
    profile = resolve_profile(args.profile)
    # lighter default for stipple
    if args.z_down is not None:
        profile.pen.z_down = args.z_down
    strokes = image_to_stipple_strokes(
        Path(args.image),
        max_points=args.points,
        width_mm=args.width,
        height_mm=args.height,
        origin=(args.ox, args.oy),
        seed=args.seed,
        lift_threshold=args.lift_threshold,
    )
    gcode, report = emit_strokes(strokes, profile, source=str(args.image), validate=not args.no_bounds_check)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(gcode, encoding="utf-8")
    print(f"Wrote {args.output} ({len(gcode.splitlines())} lines) — EXPERIMENTAL")
    print(report.message)
    if args.preview:
        render_preview(gcode_to_strokes(gcode), args.preview)
    return 0


def cmd_hwtest(args) -> int:
    from grbl_pen_plotter.hardware_test import run_hardware_test

    profile = resolve_profile(args.profile)
    return run_hardware_test(profile, port=args.port, skip_plot=args.skip_plot, verbose=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="penplot",
        description="GRBL pen-plotter sender and toolpath tools (JinGan / BtWriter class)",
    )
    p.add_argument("--version", action="version", version=f"penplot {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("ports", help="List serial ports")
    sp.set_defaults(func=cmd_ports)

    sp = sub.add_parser("status", help="Query GRBL status")
    _add_common(sp)
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("jog", help="Jog an axis")
    _add_common(sp)
    sp.add_argument("axis", choices=["X", "Y", "Z", "x", "y", "z"])
    sp.add_argument("distance", type=float)
    sp.add_argument("--feed", type=float, default=None)
    sp.set_defaults(func=cmd_jog)

    sp = sub.add_parser("zero", help="Set work zero (G92) at current raised pose")
    _add_common(sp)
    sp.set_defaults(func=cmd_zero)

    sp = sub.add_parser("pen", help="Pen up/down cycle")
    _add_common(sp)
    sp.add_argument("action", choices=["up", "down"])
    sp.set_defaults(func=cmd_pen)

    sp = sub.add_parser("svg", help="SVG → G-code")
    _add_common(sp)
    sp.add_argument("svg", type=Path)
    sp.add_argument("-o", "--output", type=Path, required=True)
    sp.add_argument("--paper", default="A4", choices=["A4", "A5", "A6"])
    sp.add_argument("--margin", type=float, default=10.0)
    sp.add_argument("--width", type=float, default=None, help="Fit width mm (overrides paper)")
    sp.add_argument("--height", type=float, default=None)
    sp.add_argument("--scale", type=float, default=None)
    sp.add_argument("--ox", type=float, default=0.0)
    sp.add_argument("--oy", type=float, default=0.0)
    sp.add_argument("--flip-x", action="store_true")
    sp.add_argument("--no-flip-y", action="store_true")
    sp.add_argument("--g92x", type=float, default=None)
    sp.add_argument("--g92y", type=float, default=None)
    sp.add_argument("--preview", type=Path, default=None)
    sp.add_argument("--no-bounds-check", action="store_true")
    sp.set_defaults(func=cmd_svg)

    sp = sub.add_parser("text", help="Text → G-code (stick font, Latin+Cyrillic)")
    _add_common(sp)
    sp.add_argument("text", nargs="?", default="")
    sp.add_argument("--file", type=Path, default=None)
    sp.add_argument("-o", "--output", type=Path, required=True)
    sp.add_argument("--em", type=float, default=0.45, help="Em scale")
    sp.add_argument("--ox", type=float, default=5.0)
    sp.add_argument("--oy", type=float, default=5.0)
    sp.add_argument("--max-width", type=float, default=160.0)
    sp.add_argument("--flip-x", action="store_true")
    sp.add_argument("--flip-y", action="store_true")
    sp.add_argument("--preview", type=Path, default=None)
    sp.add_argument("--no-bounds-check", action="store_true")
    sp.set_defaults(func=cmd_text)

    sp = sub.add_parser("preview", help="Render G-code toolpath to SVG/PNG")
    sp.add_argument("gcode", type=Path)
    sp.add_argument("-o", "--output", type=Path, required=True)
    sp.set_defaults(func=cmd_preview)

    sp = sub.add_parser("check", help="Bounds-check a G-code file")
    _add_common(sp)
    sp.add_argument("gcode", type=Path)
    sp.add_argument("--g92x", type=float, default=None)
    sp.add_argument("--g92y", type=float, default=None)
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("stream", help="Stream G-code to the plotter")
    _add_common(sp)
    sp.add_argument("gcode", type=Path)
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--set-zero", action="store_true", help="G92 at current pose before stream")
    sp.add_argument("--cool", action="store_true", help="Set $1 cool value after job")
    sp.add_argument("--preview", type=Path, default=None)
    sp.add_argument("--no-bounds-check", action="store_true")
    sp.set_defaults(func=cmd_stream)

    sp = sub.add_parser("stipple", help="EXPERIMENTAL: image → stipple G-code")
    _add_common(sp)
    sp.add_argument("image", type=Path)
    sp.add_argument("-o", "--output", type=Path, required=True)
    sp.add_argument("--points", type=int, default=2000)
    sp.add_argument("--width", type=float, default=90.0)
    sp.add_argument("--height", type=float, default=90.0)
    sp.add_argument("--ox", type=float, default=5.0)
    sp.add_argument("--oy", type=float, default=5.0)
    sp.add_argument("--seed", type=int, default=1)
    sp.add_argument("--lift-threshold", type=float, default=3.0)
    sp.add_argument("--z-down", type=float, default=13.0)
    sp.add_argument("--preview", type=Path, default=None)
    sp.add_argument("--no-bounds-check", action="store_true")
    sp.set_defaults(func=cmd_stipple)

    sp = sub.add_parser("hwtest", help="Safe hardware smoke test (if connected)")
    _add_common(sp)
    sp.add_argument("--skip-plot", action="store_true", help="Skip the 5cm square plot")
    sp.set_defaults(func=cmd_hwtest)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except GrblError as exc:
        print(f"GRBL error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
