from __future__ import annotations


def test_translate_tick_signal_to_payload():
    from tpfan_gui.ipc.dbus_client import translate_tick

    payload = translate_tick(
        {"CPU": 50.0, "GPU": 55.0},
        [(2200, 0xFF), (2100, 0xFF)],
        "auto",
    )
    assert payload.temps == {"CPU": 50.0, "GPU": 55.0}
    assert payload.fans == [(2200, "auto"), (2100, "auto")]
    assert payload.level == "auto"


def test_translate_numeric_level():
    from tpfan_gui.ipc.dbus_client import translate_tick
    payload = translate_tick({"CPU": 50.0}, [(3000, 5)], "5")
    assert payload.fans[0] == (3000, "5")
    assert payload.level == "5"
