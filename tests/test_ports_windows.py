"""Port scoring should prefer COM* on Windows-style device names."""

from grbl_pen_plotter import ports


def test_preferred_matches_com_and_ch340():
    assert ports.PREFERRED.search("USB-SERIAL CH340 (COM3)")
    assert ports.COM_RE.match("COM3")
    assert ports.COM_RE.match("com12")


def test_score_orders_com_before_bluetoothish(monkeypatch):
    monkeypatch.setattr(ports.sys, "platform", "win32")
    entries = [
        {"device": "COM1", "description": "Communications Port", "hwid": "", "manufacturer": ""},
        {
            "device": "COM3",
            "description": "USB-SERIAL CH340 (COM3)",
            "hwid": "USB VID:PID=1A86:7523",
            "manufacturer": "wch.cn",
        },
    ]
    ranked = sorted(entries, key=lambda e: ports._score(e, "usbserial"))
    assert ranked[0]["device"] == "COM3"


def test_autodetect_com_when_only_com(monkeypatch):
    monkeypatch.setattr(ports.sys, "platform", "win32")
    monkeypatch.setattr(
        ports,
        "list_ports",
        lambda: [
            {
                "device": "COM5",
                "description": "USB-SERIAL CH340 (COM5)",
                "hwid": "USB VID:PID=1A86:7523",
                "manufacturer": "",
            }
        ],
    )
    assert ports.autodetect_port() == "COM5"
