"""In-memory fake GRBL serial device for tests."""

from __future__ import annotations

import re
import threading
from collections import deque
from typing import Deque, Optional


class FakeSerial:
    """Minimal pyserial-like port that speaks a tiny GRBL dialect."""

    def __init__(self, port: str = "fake", baudrate: int = 115200, timeout: float = 0.1, **_kw):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.is_open = True
        self._rx: Deque[bytes] = deque()
        self._lock = threading.Lock()
        self.x = 40.0
        self.y = 150.0
        self.z = 947.0
        self.wco = (0.0, 0.0, 0.0)  # G92 offsets: machine = work + wco... we store work zero shift
        self.state = "Idle"
        self.settings = {"$1": "255", "$20": "0", "$32": "0"}
        self.lines_received = []
        self.alarm = False
        self._push(b"Grbl 1.3a ['$' for help]\n")

    def _push(self, data: bytes) -> None:
        with self._lock:
            self._rx.append(data)

    @property
    def in_waiting(self) -> int:
        with self._lock:
            return sum(len(x) for x in self._rx)

    def reset_input_buffer(self) -> None:
        with self._lock:
            self._rx.clear()

    def close(self) -> None:
        self.is_open = False

    def flush(self) -> None:
        pass

    def read(self, size: int = 1) -> bytes:
        with self._lock:
            if not self._rx:
                return b""
            data = self._rx[0]
            if len(data) <= size:
                self._rx.popleft()
                return data
            out, rest = data[:size], data[size:]
            self._rx[0] = rest
            return out

    def write(self, data: bytes) -> int:
        if data == b"\x18":
            self.state = "Idle"
            self.alarm = False
            self._push(b"\r\nGrbl 1.3a ['$' for help]\n")
            return len(data)
        if data == b"?":
            # Report work pos if G92 applied (wco stored as machine-at-zero)
            wx = self.x - self.wco[0]
            wy = self.y - self.wco[1]
            wz = self.z - self.wco[2]
            # Prefer MPos like $10=1 machines
            msg = f"<{self.state}|MPos:{self.x:.3f},{self.y:.3f},{self.z:.3f}|WPos:{wx:.3f},{wy:.3f},{wz:.3f}|FS:0,0>\n"
            self._push(msg.encode("utf-8"))
            return len(data)
        if data in (b"!", b"~"):
            return len(data)

        text = data.decode("utf-8", errors="replace")
        for raw in text.split("\n"):
            line = raw.strip()
            if not line:
                continue
            self.lines_received.append(line)
            self._handle_line(line)
        return len(data)

    def _ok(self) -> None:
        self._push(b"ok\n")

    def _handle_line(self, line: str) -> None:
        if self.alarm and line != "$X":
            self._push(b"error:9\n")
            return
        if line == "$X":
            self.alarm = False
            self.state = "Idle"
            self._ok()
            return
        if line.startswith("$1="):
            self.settings["$1"] = line.split("=", 1)[1]
            self._ok()
            return
        if line in ("$1", "$20", "$32"):
            key = line
            self._push(f"{key}={self.settings.get(key, '0')}\n".encode())
            self._ok()
            return
        if line.startswith("$J="):
            # $J=G91 X1 F800
            m = re.search(r"([XYZ])\s*([-\d.]+)", line, re.I)
            if m:
                axis, val = m.group(1).upper(), float(m.group(2))
                if axis == "X":
                    self.x += val
                elif axis == "Y":
                    self.y += val
                else:
                    self.z += val
            self._ok()
            return
        if line.upper().startswith("G92"):
            # Set work zero at current machine pose
            self.wco = (self.x, self.y, self.z)
            self._ok()
            return
        if line.upper() in ("M3 S1000", "M3S1000") or line.upper().startswith("M3"):
            self._ok()
            return
        if line.upper() in ("M5", "S0") or line.upper().startswith("M5"):
            self._ok()
            return
        if line.upper() in ("G21", "G90", "G94"):
            self._ok()
            return
        # G0 / G1 moves
        m = re.match(r"G0?([01])\b(.*)", line, re.I)
        if m:
            rest = m.group(2)
            for axis, val in re.findall(r"([XYZ])\s*([-\d.]+)", rest, re.I):
                v = float(val)
                # absolute work → machine
                if axis.upper() == "X":
                    self.x = self.wco[0] + v
                elif axis.upper() == "Y":
                    self.y = self.wco[1] + v
                else:
                    self.z = self.wco[2] + v
            self._ok()
            return
        if line.upper() == "ALARM":
            self.alarm = True
            self.state = "Alarm"
            self._push(b"ALARM:1\n")
            return
        # default accept
        self._ok()
