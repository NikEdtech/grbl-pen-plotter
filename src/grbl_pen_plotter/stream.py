"""G-code streaming with ok/flow control, resume, and abort."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from grbl_pen_plotter.grbl import AlarmError, Grbl, GrblError
from grbl_pen_plotter.profile import Profile


def normalize_gcode(text: str) -> List[str]:
    cmds: List[str] = []
    for raw in text.splitlines():
        line = raw.split(";")[0].strip()
        if line:
            cmds.append(line)
    return cmds


@dataclass
class StreamResult:
    ok: bool
    lines_sent: int
    total: int
    error: Optional[str] = None
    aborted: bool = False


@dataclass
class StreamController:
    grbl: Grbl
    commands: List[str]
    profile: Optional[Profile] = None
    on_progress: Optional[Callable[[int, int, str], None]] = None
    _index: int = 0
    _paused: bool = False
    _abort: bool = False
    sent: List[str] = field(default_factory=list)

    @classmethod
    def from_text(cls, grbl: Grbl, text: str, profile: Optional[Profile] = None) -> "StreamController":
        return cls(grbl=grbl, commands=normalize_gcode(text), profile=profile)

    def pause(self) -> None:
        self._paused = True
        self.grbl.feed_hold()

    def resume(self) -> None:
        self._paused = False
        self.grbl.cycle_start()

    def abort(self) -> None:
        self._abort = True
        self.grbl.aborted = True

    def run(self, *, start_at: int = 0, poll_status_every: int = 50) -> StreamResult:
        self._index = max(0, start_at)
        total = len(self.commands)
        try:
            while self._index < total:
                if self._abort:
                    self.grbl.abort_safe(self.profile)
                    return StreamResult(
                        ok=False,
                        lines_sent=len(self.sent),
                        total=total,
                        error="aborted",
                        aborted=True,
                    )
                while self._paused and not self._abort:
                    import time

                    time.sleep(0.05)
                cmd = self.commands[self._index]
                try:
                    self.grbl.send(cmd, timeout=60)
                except AlarmError as exc:
                    self.grbl.abort_safe(self.profile)
                    return StreamResult(
                        ok=False,
                        lines_sent=len(self.sent),
                        total=total,
                        error=str(exc),
                        aborted=True,
                    )
                except GrblError as exc:
                    self.grbl.abort_safe(self.profile)
                    return StreamResult(
                        ok=False,
                        lines_sent=len(self.sent),
                        total=total,
                        error=str(exc),
                    )
                self.sent.append(cmd)
                self._index += 1
                if self.on_progress:
                    self.on_progress(self._index, total, cmd)
                if poll_status_every and self._index % poll_status_every == 0:
                    st = self.grbl.status()
                    if st and "Alarm" in st.state:
                        self.grbl.abort_safe(self.profile)
                        return StreamResult(
                            ok=False,
                            lines_sent=len(self.sent),
                            total=total,
                            error=f"Alarm state: {st.raw}",
                            aborted=True,
                        )
            self.grbl.wait_idle(timeout=180)
            return StreamResult(ok=True, lines_sent=len(self.sent), total=total)
        except AlarmError as exc:
            self.grbl.abort_safe(self.profile)
            return StreamResult(
                ok=False,
                lines_sent=len(self.sent),
                total=total,
                error=str(exc),
                aborted=True,
            )


def stream_file(grbl: Grbl, text: str, profile: Optional[Profile] = None, **kwargs) -> StreamResult:
    ctrl = StreamController.from_text(grbl, text, profile=profile)
    if "on_progress" in kwargs:
        ctrl.on_progress = kwargs.pop("on_progress")
    return ctrl.run(**kwargs)
