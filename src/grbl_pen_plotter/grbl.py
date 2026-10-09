"""GRBL serial connection: handshake, status, jog, pen helpers."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, TextIO, Union

import serial

from grbl_pen_plotter.profile import Profile

LogFn = Callable[[str, str], None]


@dataclass
class Status:
    state: str
    x: float
    y: float
    z: float
    raw: str
    wpos: bool = False  # True if coords came from WPos


class GrblError(RuntimeError):
    pass


class AlarmError(GrblError):
    pass


class Grbl:
    """Minimal synchronous GRBL client with ok/error flow control."""

    def __init__(
        self,
        port: str,
        baud: int = 115200,
        *,
        timeout: float = 0.1,
        log: Optional[LogFn] = None,
        serial_factory: Optional[Callable[..., serial.Serial]] = None,
    ) -> None:
        self.port = port
        self.baud = baud
        self._log = log or (lambda _k, _m: None)
        self._factory = serial_factory or serial.Serial
        self._ser: Optional[serial.Serial] = None
        self._rx_buf = ""
        self.aborted = False

    @property
    def ser(self) -> serial.Serial:
        if self._ser is None:
            raise GrblError("Not connected")
        return self._ser

    def connect(self, soft_reset: bool = True) -> List[str]:
        self._ser = self._factory(self.port, self.baud, timeout=0.1)
        time.sleep(0.2)
        try:
            self._ser.reset_input_buffer()
        except Exception:
            pass
        welcome: List[str] = []
        if soft_reset:
            welcome = self.soft_reset()
        return welcome

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    def __enter__(self) -> "Grbl":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _emit(self, kind: str, msg: str) -> None:
        self._log(kind, msg)

    def soft_reset(self) -> List[str]:
        self._emit("TX", "SOFT_RESET (0x18)")
        self.ser.write(b"\x18")
        self.ser.flush()
        time.sleep(2.0)
        lines = self._drain(duration=2.5)
        try:
            self.ser.reset_input_buffer()
        except Exception:
            pass
        self._rx_buf = ""
        return lines

    def _drain(self, duration: float = 1.0) -> List[str]:
        deadline = time.time() + duration
        lines: List[str] = []
        buf = self._rx_buf
        while time.time() < deadline:
            chunk = self.ser.read(self.ser.in_waiting or 1)
            if chunk:
                buf += chunk.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line:
                        self._emit("RX", line)
                        lines.append(line)
            else:
                time.sleep(0.02)
        self._rx_buf = buf
        return lines

    def read_until(
        self,
        timeout: float = 30.0,
        *,
        stop_on_ok: bool = True,
    ) -> tuple:
        """Return (status, lines) where status is ok|error|alarm|timeout."""
        deadline = time.time() + timeout
        lines: List[str] = []
        buf = self._rx_buf
        while time.time() < deadline:
            if self.aborted:
                return "abort", lines
            chunk = self.ser.read(self.ser.in_waiting or 1)
            if chunk:
                buf += chunk.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    self._emit("RX", line)
                    lines.append(line)
                    low = line.lower()
                    if stop_on_ok and low == "ok":
                        self._rx_buf = buf
                        return "ok", lines
                    if low.startswith("error"):
                        self._rx_buf = buf
                        return "error", lines
                    if "ALARM" in line or low.startswith("alarm"):
                        self._rx_buf = buf
                        return "alarm", lines
            else:
                time.sleep(0.01)
        self._rx_buf = buf
        return "timeout", lines

    def send(
        self,
        cmd: str,
        *,
        timeout: float = 30.0,
        wait_ok: bool = True,
    ) -> tuple:
        if self.aborted:
            raise GrblError("Aborted")
        self._emit("TX", cmd)
        self.ser.write((cmd + "\n").encode("utf-8"))
        self.ser.flush()
        if not wait_ok:
            return "sent", []
        status, lines = self.read_until(timeout=timeout)
        if status == "alarm":
            raise AlarmError(f"ALARM after {cmd!r}: {lines}")
        if status == "error":
            raise GrblError(f"error after {cmd!r}: {lines}")
        if status == "timeout":
            raise GrblError(f"timeout waiting for ok after {cmd!r}")
        if status == "abort":
            raise GrblError("Aborted")
        return status, lines

    def realtime(self, byte: bytes, label: str) -> None:
        self._emit("TX", label)
        self.ser.write(byte)
        self.ser.flush()

    def feed_hold(self) -> None:
        self.realtime(b"!", "FEED_HOLD")

    def cycle_start(self) -> None:
        self.realtime(b"~", "CYCLE_START")

    def status(self, timeout: float = 2.0) -> Optional[Status]:
        self.ser.write(b"?")
        self.ser.flush()
        deadline = time.time() + timeout
        buf = ""
        while time.time() < deadline:
            chunk = self.ser.read(self.ser.in_waiting or 1)
            if chunk:
                buf += chunk.decode("utf-8", errors="replace")
                m = re.search(r"<([^>]+)>", buf)
                if m:
                    raw = m.group(1)
                    self._emit("STATUS", raw)
                    state = raw.split("|")[0]
                    wm = re.search(r"WPos:([-\d.]+),([-\d.]+),([-\d.]+)", raw)
                    mm = re.search(r"MPos:([-\d.]+),([-\d.]+),([-\d.]+)", raw)
                    if wm:
                        return Status(
                            state=state,
                            x=float(wm.group(1)),
                            y=float(wm.group(2)),
                            z=float(wm.group(3)),
                            raw=raw,
                            wpos=True,
                        )
                    if mm:
                        return Status(
                            state=state,
                            x=float(mm.group(1)),
                            y=float(mm.group(2)),
                            z=float(mm.group(3)),
                            raw=raw,
                            wpos=False,
                        )
            else:
                time.sleep(0.02)
        self._emit("SYS", f"status timeout buf={buf!r}")
        return None

    def wait_idle(self, timeout: float = 120.0) -> Optional[Status]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            st = self.status(timeout=1.5)
            if st and st.state == "Idle":
                return st
            if st and "Alarm" in st.state:
                raise AlarmError(f"Alarm while waiting Idle: {st.raw}")
            time.sleep(0.12)
        return None

    def unlock(self) -> None:
        self.send("$X", timeout=5)

    def set_step_idle(self, value: int) -> None:
        self.send(f"$1={int(value)}", timeout=5)

    def query_setting(self, key: str) -> str:
        """Send e.g. '$1' and return joined response lines."""
        _status, lines = self.send(key, timeout=5)
        return "\n".join(lines)

    def ensure_plotting_hold(self, profile: Profile) -> None:
        want = profile.grbl.step_idle_plotting
        blob = self.query_setting("$1")
        if f"$1={want}" not in blob:
            self.set_step_idle(want)
            self.soft_reset()
            self.unlock()

    def cool_motors(self, profile: Profile) -> None:
        self.set_step_idle(profile.grbl.step_idle_cool)
        self.soft_reset()
        self.unlock()

    def set_work_zero(self) -> None:
        """G92 X0 Y0 Z0 at current pose (raised pen at sheet corner)."""
        self.send("G21", timeout=5)
        self.send("G90", timeout=5)
        self.send("G92 X0 Y0 Z0", timeout=5)

    def pen_up(self, profile: Profile) -> None:
        p = profile.pen
        self.send(f"G0 Z{p.z_up:.3f} F{p.z_feed:.0f}", timeout=15)
        self.send(p.spindle_off, timeout=5)
        self.send("S0", timeout=5)

    def pen_down(self, profile: Profile) -> None:
        p = profile.pen
        if p.hold_spindle_during_stroke:
            self.send(p.spindle_on, timeout=5)
        self.send(f"G0 Z{p.z_down:.3f} F{p.z_feed:.0f}", timeout=15)

    def jog(self, axis: str, distance: float, feed: Optional[float] = None, profile: Optional[Profile] = None) -> None:
        axis = axis.upper()
        if axis not in {"X", "Y", "Z"}:
            raise ValueError("axis must be X, Y, or Z")
        f = feed if feed is not None else (profile.feeds.jog if profile else 1000.0)
        # GRBL jog: $J=G91 X… F…
        self.send(f"$J=G91 {axis}{distance:.3f} F{f:.0f}", timeout=30)

    def abort_safe(self, profile: Optional[Profile] = None) -> None:
        self.aborted = True
        self._emit("SYS", "ABORT — soft-reset + pen up")
        try:
            self.ser.write(b"\x18")
            self.ser.flush()
            time.sleep(1.5)
            try:
                self.ser.reset_input_buffer()
            except Exception:
                pass
            self.aborted = False
            self.send("M5", timeout=10)
            z_up = profile.pen.z_up if profile else 0.0
            self.send(f"G0 Z{z_up:.1f} F800", timeout=10)
            self.send("S0", timeout=5)
        except Exception as exc:
            self._emit("SYS", f"abort cleanup error: {exc}")
            self.aborted = True


def make_logger(fp: Optional[TextIO] = None) -> LogFn:
    def _log(kind: str, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        line = f"{ts} [{kind}] {msg}"
        print(line)
        if fp is not None:
            fp.write(line + "\n")
            fp.flush()

    return _log
