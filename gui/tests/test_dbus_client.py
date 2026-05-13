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


def test_translate_disengaged_distinct_from_auto():
    from tpfan_gui.ipc.dbus_client import translate_tick
    payload = translate_tick({}, [(3000, 0xFE)], "disengaged")
    assert payload.fans == [(3000, "disengaged")]
    assert payload.level == "disengaged"


class _DummyClient:
    """_ProxyOps-Konsument zum Testen ohne PyQt6/D-Bus."""

    def __init__(self, proxy=None):
        self._proxy = proxy


def test_set_methods_raise_when_disconnected():
    import pytest
    from tpfan_gui.ipc.dbus_client import _ProxyOps, DaemonNotConnected

    class C(_ProxyOps, _DummyClient):
        pass

    c = C(proxy=None)
    with pytest.raises(DaemonNotConnected):
        c.set_mode("auto")
    with pytest.raises(DaemonNotConnected):
        c.set_curve([(40.0, 0)], ["CPU"])
    with pytest.raises(DaemonNotConnected):
        c.set_manual_level("3")
    with pytest.raises(DaemonNotConnected):
        c.set_failsafe_temp(95.0)
    with pytest.raises(DaemonNotConnected):
        c.reload_config()
    # get() bleibt None-tolerant (Read-only-Vertrag)
    assert c.get("Mode") is None


def test_set_methods_delegate_when_connected():
    from tpfan_gui.ipc.dbus_client import _ProxyOps

    class FakeProxy:
        def __init__(self):
            self.calls = []
        def SetMode(self, m): self.calls.append(("SetMode", m))
        def SetCurve(self, p, s): self.calls.append(("SetCurve", p, s))
        def SetManualLevel(self, lvl): self.calls.append(("SetManualLevel", lvl))
        def SetFailsafeTemp(self, t): self.calls.append(("SetFailsafeTemp", t))
        def ReloadConfig(self): self.calls.append(("ReloadConfig",))
        Mode = "auto"

    class C(_ProxyOps, _DummyClient):
        pass

    proxy = FakeProxy()
    c = C(proxy=proxy)
    c.set_mode("manual")
    c.set_curve([(40.0, 0)], ["CPU"])
    c.set_manual_level("3")
    c.set_failsafe_temp(95.0)
    c.reload_config()
    assert proxy.calls == [
        ("SetMode", "manual"),
        ("SetCurve", [(40.0, 0)], ["CPU"]),
        ("SetManualLevel", "3"),
        ("SetFailsafeTemp", 95.0),
        ("ReloadConfig",),
    ]
    assert c.get("Mode") == "auto"
