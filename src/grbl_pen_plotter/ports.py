"""Serial port discovery for macOS / Linux CH340 plotters."""

from __future__ import annotations

import re
from typing import Dict, List, Optional

import serial.tools.list_ports

PREFERRED = re.compile(
    r"(usbserial|wchusbserial|cu\.usbserial|tty\.usbserial|CH340|ch34|ttyUSB|ttyACM)",
    re.I,
)


def list_ports() -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for p in serial.tools.list_ports.comports():
        out.append(
            {
                "device": p.device,
                "description": p.description or "",
                "hwid": p.hwid or "",
                "manufacturer": getattr(p, "manufacturer", None) or "",
            }
        )
    return out


def _score(entry: Dict[str, str], hint: str = "usbserial") -> tuple:
    blob = " ".join(entry.values())
    preferred = 0 if PREFERRED.search(blob) else 1
    hint_hit = 0 if hint and hint.lower() in blob.lower() else 1
    # Prefer cu.* over tty.* on macOS (avoid locking both ends)
    cu = 0 if entry["device"].startswith("/dev/cu.") else 1
    return (preferred, hint_hit, cu, entry["device"])


def autodetect_port(hint: str = "usbserial") -> Optional[str]:
    ports = list_ports()
    if not ports:
        return None
    ranked = sorted(ports, key=lambda e: _score(e, hint))
    best = ranked[0]
    if PREFERRED.search(" ".join(best.values())) or (hint and hint.lower() in " ".join(best.values()).lower()):
        return best["device"]
    # Fall back to first cu.usb* style even if description empty
    for e in ranked:
        if "usbserial" in e["device"].lower() or "ttyUSB" in e["device"] or "ttyACM" in e["device"]:
            return e["device"]
    return None
