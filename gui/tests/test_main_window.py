from __future__ import annotations
import pytest

pytest.importorskip("pytestqt")


class _FakeClient:
    """Minimal fake DBus client exposing the signals/methods MainWindow needs."""
    def __init__(self):
        from PyQt6.QtCore import QObject, pyqtSignal

        class _Signals(QObject):
            tickReceived = pyqtSignal(object)
            emergency = pyqtSignal(float, str)
            connected = pyqtSignal(bool)

        self._s = _Signals()
        self.tickReceived = self._s.tickReceived
        self.emergency = self._s.emergency
        self.connected = self._s.connected
        self.mode_calls: list[str] = []
        self.manual_calls: list[str] = []
        self.failsafe_calls: list[float] = []
        self.curve_calls: list = []
        self.save_calls: list = []
        self.delete_calls: list[str] = []
        self.props: dict = {}

    def set_mode(self, m: str): self.mode_calls.append(m)
    def set_manual_level(self, v: str): self.manual_calls.append(v)
    def set_failsafe_temp(self, t: float): self.failsafe_calls.append(t)
    def set_curve(self, points, sensors): self.curve_calls.append((list(points), list(sensors)))
    def get(self, name): return self.props.get(name)
    def save_user_preset(self, name, points, sensors):
        self.save_calls.append((name, list(points), list(sensors)))
    def delete_user_preset(self, name):
        self.delete_calls.append(name)


def test_mode_request_propagates_state(qtbot):
    from tpfan_gui.main_window import MainWindow
    client = _FakeClient()
    win = MainWindow(client)
    qtbot.addWidget(win)

    win.modes.modeRequested.emit("manual")
    assert client.mode_calls == ["manual"]
    assert all(b.isEnabled() for b in win.modes._manual_buttons)

    win.modes.modeRequested.emit("auto")
    assert client.mode_calls == ["manual", "auto"]
    assert all(not b.isEnabled() for b in win.modes._manual_buttons)


def test_send_curve_switches_to_curve_mode(qtbot):
    from tpfan_gui.main_window import MainWindow
    client = _FakeClient()
    win = MainWindow(client)
    qtbot.addWidget(win)

    pts = [(40.0, 0), (60.0, 4), (80.0, 7)]
    win._send_curve(pts)

    assert client.curve_calls == [(pts, ["CPU", "GPU", "NVMe"])]
    assert client.mode_calls == ["curve"]
    assert all(not b.isEnabled() for b in win.modes._manual_buttons)


def test_send_curve_does_not_switch_mode_if_set_curve_fails(qtbot):
    from tpfan_gui.main_window import MainWindow
    client = _FakeClient()

    def boom(points, sensors):
        raise RuntimeError("polkit denied")

    client.set_curve = boom
    win = MainWindow(client)
    qtbot.addWidget(win)

    win._send_curve([(40.0, 0), (80.0, 7)])
    assert client.mode_calls == []


def test_reconnect_resets_t0(qtbot):
    from tpfan_gui.main_window import MainWindow
    client = _FakeClient()
    win = MainWindow(client)
    qtbot.addWidget(win)

    win._t0 = 123.0
    win._on_connected(False)
    assert win._t0 == 123.0
    win._on_connected(True)
    assert win._t0 is None


def test_friendly_error_maps_polkit_and_disconnected():
    from tpfan_gui.main_window import MainWindow
    assert "polkit" in MainWindow._friendly_error(RuntimeError("AccessDenied: blah")).lower() \
        or "Berechtigung" in MainWindow._friendly_error(RuntimeError("AccessDenied: blah"))
    assert MainWindow._friendly_error(RuntimeError("polkit denied")) == "Keine Berechtigung (polkit verweigert)"
    assert MainWindow._friendly_error(RuntimeError("daemon not connected")) == "Daemon nicht verbunden"
    assert MainWindow._friendly_error(RuntimeError("something else")) == "something else"


def test_main_window_syncs_user_presets_on_connect(qtbot):
    from tpfan_gui.main_window import MainWindow
    client = _FakeClient()
    client.props = {
        "Curve": [(40.0, 0), (80.0, 7)],
        "UserPresets": {"Meins": ([(42.0, 0), (80.0, 7)], ["CPU"])},
    }
    w = MainWindow(client)
    qtbot.addWidget(w)
    client.connected.emit(True)
    names = [b.text() for b in w.curve_editor.user_preset_buttons]
    assert names == ["Meins"]


def test_main_window_save_preset_calls_client(qtbot, monkeypatch):
    from tpfan_gui.main_window import MainWindow
    from PyQt6 import QtWidgets

    client = _FakeClient()
    client.props = {"Curve": [(40.0, 0), (80.0, 7)], "UserPresets": {}}

    monkeypatch.setattr(QtWidgets.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Mein", True)))
    w = MainWindow(client)
    qtbot.addWidget(w)
    client.connected.emit(True)
    w.curve_editor.save_as_btn.click()
    assert len(client.save_calls) == 1
    name, pts, sensors = client.save_calls[0]
    assert name == "Mein"
    assert sensors == ["CPU", "GPU", "NVMe"]
