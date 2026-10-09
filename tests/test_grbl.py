from grbl_pen_plotter.grbl import Grbl
from grbl_pen_plotter.profile import resolve_profile
from grbl_pen_plotter.stream import stream_file
from tests.fake_grbl import FakeSerial


def test_connect_status_jog_pen():
    profile = resolve_profile("jingan")
    ser = FakeSerial()
    g = Grbl("fake", 115200, serial_factory=lambda *a, **k: ser)
    g.connect(soft_reset=True)
    st = g.status()
    assert st is not None
    assert st.state == "Idle"
    g.jog("X", 1.0, profile=profile)
    assert abs(ser.x - 41.0) < 0.01
    g.set_work_zero()
    g.pen_down(profile)
    assert abs((ser.z - ser.wco[2]) - profile.pen.z_down) < 0.01
    g.pen_up(profile)
    assert abs((ser.z - ser.wco[2]) - profile.pen.z_up) < 0.01
    g.close()


def test_stream_ok_flow():
    profile = resolve_profile("jingan")
    ser = FakeSerial()
    g = Grbl("fake", 115200, serial_factory=lambda *a, **k: ser)
    g.connect(soft_reset=True)
    g.set_work_zero()
    gcode = "\n".join(
        [
            "G21",
            "G90",
            "M5",
            "G0 Z0",
            "G0 X5 Y5 F2500",
            "M3 S1000",
            "G0 Z15",
            "G1 X15 Y5 F800",
            "G1 X15 Y15 F800",
            "G0 Z0",
            "M5",
        ]
    )
    result = stream_file(g, gcode, profile=profile)
    assert result.ok
    assert result.lines_sent == result.total
    g.close()


def test_alarm_aborts():
    ser = FakeSerial()
    g = Grbl("fake", 115200, serial_factory=lambda *a, **k: ser)
    g.connect(soft_reset=False)
    ser.alarm = True
    ser.state = "Alarm"
    result = stream_file(g, "G0 X1\nG0 X2\n")
    assert not result.ok
    g.close()
