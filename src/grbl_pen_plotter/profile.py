"""Load machine / pen profiles from TOML."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


@dataclass
class PenConfig:
    mode: str = "z_stepper"  # z_stepper | servo_pwm
    z_up: float = 0.0
    z_down: float = 15.0
    z_feed: float = 800.0
    spindle_on: str = "M3 S1000"
    spindle_off: str = "M5"
    hold_spindle_during_stroke: bool = True


@dataclass
class Feeds:
    rapid: float = 2500.0
    draw: float = 800.0
    jog: float = 1000.0


@dataclass
class SoftLimits:
    x_min: float = 0.0
    x_max: float = 180.0
    y_min: float = 0.0
    y_max: float = 280.0
    margin: float = 5.0
    # Optional machine-space clamp after G92 (absolute work + origin)
    machine_x_min: Optional[float] = None
    machine_x_max: Optional[float] = None
    machine_y_min: Optional[float] = None
    machine_y_max: Optional[float] = None


@dataclass
class GrblPolicy:
    baud: int = 115200
    step_idle_plotting: int = 255  # $1 while plotting
    step_idle_cool: int = 25  # $1 when idle / cooling
    laser_mode: int = 0  # $32 must stay 0 for pen machines
    soft_reset_on_connect: bool = True
    home_on_connect: bool = False


@dataclass
class PaperSize:
    name: str
    width_mm: float
    height_mm: float


PAPER = {
    "A4": PaperSize("A4", 210.0, 297.0),
    "A5": PaperSize("A5", 148.0, 210.0),
    "A6": PaperSize("A6", 105.0, 148.0),
}


@dataclass
class Profile:
    name: str
    description: str = ""
    pen: PenConfig = field(default_factory=PenConfig)
    feeds: Feeds = field(default_factory=Feeds)
    limits: SoftLimits = field(default_factory=SoftLimits)
    grbl: GrblPolicy = field(default_factory=GrblPolicy)
    default_port_hint: str = "usbserial"
    notes: str = ""

    @property
    def work_width(self) -> float:
        return max(0.0, self.limits.x_max - self.limits.x_min)

    @property
    def work_height(self) -> float:
        return max(0.0, self.limits.y_max - self.limits.y_min)


def _section(data: Dict[str, Any], key: str) -> Dict[str, Any]:
    val = data.get(key) or {}
    if not isinstance(val, dict):
        raise ValueError(f"Profile section [{key}] must be a table")
    return val


def profile_from_dict(data: Dict[str, Any]) -> Profile:
    pen_d = _section(data, "pen")
    feeds_d = _section(data, "feeds")
    limits_d = _section(data, "limits")
    grbl_d = _section(data, "grbl")
    return Profile(
        name=str(data.get("name", "unnamed")),
        description=str(data.get("description", "")),
        pen=PenConfig(**{k: pen_d[k] for k in PenConfig.__dataclass_fields__ if k in pen_d}),
        feeds=Feeds(**{k: feeds_d[k] for k in Feeds.__dataclass_fields__ if k in feeds_d}),
        limits=SoftLimits(
            **{k: limits_d[k] for k in SoftLimits.__dataclass_fields__ if k in limits_d}
        ),
        grbl=GrblPolicy(**{k: grbl_d[k] for k in GrblPolicy.__dataclass_fields__ if k in grbl_d}),
        default_port_hint=str(data.get("default_port_hint", "usbserial")),
        notes=str(data.get("notes", "")),
    )


def load_profile(path: Path) -> Profile:
    raw = path.read_bytes()
    data = tomllib.loads(raw.decode("utf-8"))
    return profile_from_dict(data)


def default_profiles_dir() -> Path:
    # Installed package data / repo profiles/
    here = Path(__file__).resolve()
    candidates = [
        here.parent / "data",
        here.parents[2] / "profiles",  # src layout: repo/profiles
        here.parents[1] / "profiles",
        Path.cwd() / "profiles",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[0]


def resolve_profile(name_or_path: str) -> Profile:
    p = Path(name_or_path)
    if p.suffix.lower() in {".toml", ".tml"} and p.is_file():
        return load_profile(p)
    stem = name_or_path[:-5] if name_or_path.endswith(".toml") else name_or_path
    here = Path(__file__).resolve().parent
    search = [
        here / "data" / f"{stem}.toml",
        default_profiles_dir() / f"{stem}.toml",
        Path.cwd() / "profiles" / f"{stem}.toml",
        Path.cwd() / f"{stem}.toml",
    ]
    for candidate in search:
        if candidate.is_file():
            return load_profile(candidate)
    raise FileNotFoundError(
        f"Profile not found: {name_or_path!r} (tried {[str(s) for s in search]})"
    )
