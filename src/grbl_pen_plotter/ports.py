"""Serial port discovery for macOS / Windows / Linux CH340 plotters."""

from __future__ import annotations

import re
import sys
from typing import Dict, List, Optional

import serial.tools.list_ports

# macOS cu.usbserial / Linux ttyUSB / Windows COMn + common USB-UART chips
PREFERRED = re.compile(
    r"("
    r"usbserial|wchusbserial|cu\.usbserial|tty\.usbserial|"
    r"CH340|ch34|CP210|cp210|FTDI|ftdi|"
    r"ttyUSB|ttyACM|"
    r"USB.?Serial|usb.?to.?serial|"
    r"COM\d+"
    r")",
    re.I,
)

COM_RE = re.compile(r"^COM\d+$", re.I)


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


_USB_UART = re.compile(r"(CH340|ch34|CP210|cp210|FTDI|ftdi|USB.?Serial|wch|usbserial)", re.I)


def _score(entry: Dict[str, str], hint: str = "usbserial") -> tuple:
    blob = " ".join(entry.values())
    device = entry["device"]
    # 0 = USB-UART chip, 1 = generic COM/tty match, 2 = other
    if _USB_UART.search(blob):
        chip = 0
    elif COM_RE.match(device) or PREFERRED.search(blob):
        chip = 1
    else:
        chip = 2
    hint_hit = 0 if hint and hint.lower() in blob.lower() else 1
    if sys.platform == "darwin":
        platform_pref = 0 if device.startswith("/dev/cu.") else 1
    elif sys.platform == "win32":
        m = COM_RE.match(device)
        platform_pref = int(m.group(0)[3:]) if m else 99
    else:
        platform_pref = 0 if ("ttyUSB" in device or "ttyACM" in device) else 1
    return (chip, hint_hit, platform_pref, device)


def autodetect_port(hint: str = "usbserial") -> Optional[str]:
    ports = list_ports()
    if not ports:
        return None
    ranked = sorted(ports, key=lambda e: _score(e, hint))
    best = ranked[0]
    blob = " ".join(best.values())
    if PREFERRED.search(blob) or (hint and hint.lower() in blob.lower()) or COM_RE.match(best["device"]):
        # On Windows, accept a lone COM port even if description is empty
        if sys.platform == "win32" and COM_RE.match(best["device"]):
            return best["device"]
        if PREFERRED.search(blob) or (hint and hint.lower() in blob.lower()):
            return best["device"]
    for e in ranked:
        d = e["device"]
        if (
            "usbserial" in d.lower()
            or "ttyUSB" in d
            or "ttyACM" in d
            or COM_RE.match(d)
        ):
            return d
    return None
