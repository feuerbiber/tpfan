from __future__ import annotations
from PyQt6.QtWidgets import QMainWindow, QTabWidget, QStatusBar, QMessageBox

from .ipc.dbus_client import TickPayload
from .views.dashboard import Dashboard
from .views.history import make_widget as make_history
from .views.curve_editor import CurveModel, make_widget as make_curve_editor
from .views.modes import ModesPanel
from .views.status import StatusView


class MainWindow(QMainWindow):
    def __init__(self, client):
        super().__init__()
        self.setWindowTitle("tpfan")
        self.client = client

        self.curve_model = CurveModel(points=[(40.0, 0), (55.0, 2), (70.0, 4), (80.0, 7)])
        self.dashboard = Dashboard()
        self.history = make_history()
        self.curve_editor = make_curve_editor(
            self.curve_model, self._send_curve,
            on_save_preset=self._save_user_preset,
            on_delete_preset=self._delete_user_preset,
        )
        self.modes = ModesPanel(profiles=["quiet", "balanced", "performance"])
        self.status = StatusView(client)

        tabs = QTabWidget()
        tabs.addTab(self.dashboard, "Übersicht")
        tabs.addTab(self.history, "Verlauf")
        tabs.addTab(self.curve_editor, "Kurve")
        tabs.addTab(self.modes, "Modus")
        tabs.addTab(self.status, "Status")
        self.tabs = tabs
        tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(tabs)
        self.setStatusBar(QStatusBar())

        client.tickReceived.connect(self._on_tick)
        client.emergency.connect(self._on_emergency)
        client.connected.connect(self._on_connected)

        self.modes.modeRequested.connect(self._send_mode)
        self.modes.manualLevelRequested.connect(self._wrap(self.client.set_manual_level))
        self.modes.failsafeRequested.connect(self._wrap(self.client.set_failsafe_temp))

        self._t0 = None

    @staticmethod
    def _friendly_error(e: Exception) -> str:
        msg = str(e)
        low = msg.lower()
        if "accessdenied" in low or "polkit" in low or "not authorized" in low:
            return "Keine Berechtigung (polkit verweigert)"
        if "not connected" in low or "daemonnotconnected" in low:
            return "Daemon nicht verbunden"
        return msg

    def _wrap(self, fn):
        def call(*args):
            try:
                fn(*args)
            except Exception as e:
                QMessageBox.warning(self, "tpfan", self._friendly_error(e))
        return call

    def _send_mode(self, mode: str):
        try:
            self.client.set_mode(mode)
            self.modes.set_mode_state(mode)
        except Exception as e:
            QMessageBox.warning(self, "tpfan", self._friendly_error(e))

    def _send_curve(self, points):
        sensors = ["CPU", "GPU", "NVMe"]
        try:
            self.client.set_curve(points, sensors)
            self.client.set_mode("curve")
            self.modes.set_mode_state("curve")
        except Exception as e:
            QMessageBox.warning(self, "tpfan", self._friendly_error(e))

    def _save_user_preset(self, name: str, points):
        sensors = ["CPU", "GPU", "NVMe"]
        try:
            self.client.save_user_preset(name, list(points), sensors)
            self._sync_user_presets_from_daemon()
        except Exception as e:
            QMessageBox.warning(self, "tpfan", self._friendly_error(e))

    def _delete_user_preset(self, name: str):
        try:
            self.client.delete_user_preset(name)
            self._sync_user_presets_from_daemon()
        except Exception as e:
            QMessageBox.warning(self, "tpfan", self._friendly_error(e))

    def _sync_user_presets_from_daemon(self) -> None:
        try:
            presets = self.client.get("UserPresets")
        except Exception:
            return
        if presets is None:
            return
        normalized = {}
        for name, val in dict(presets).items():
            try:
                points, sensors = val
                normalized[str(name)] = (
                    [(float(t), int(l)) for t, l in points],
                    [str(s) for s in sensors],
                )
            except (TypeError, ValueError):
                continue
        setter = getattr(self.curve_editor, "set_user_presets", None)
        if callable(setter):
            setter(normalized)

    def _on_tab_changed(self, index: int) -> None:
        if self.tabs.widget(index) is self.status:
            self.status.refresh()

    def _on_tick(self, payload: TickPayload):
        self.dashboard.apply_tick(payload)
        import time
        t = time.monotonic()
        if self._t0 is None:
            self._t0 = t
        self.history.append(t - self._t0, payload.temps)
        if self.tabs.currentWidget() is self.status:
            self.status.refresh()

    def _on_emergency(self, temp: float, sensor: str):
        QMessageBox.critical(self, "Failsafe ausgelöst",
                             f"Failsafe wegen {sensor} bei {temp:.1f} °C aktiviert.")

    def _on_connected(self, ok: bool):
        self.statusBar().showMessage("Verbunden" if ok else "Daemon nicht erreichbar")
        if ok:
            self._t0 = None
            self._sync_curve_from_daemon()
            self._sync_user_presets_from_daemon()

    def _sync_curve_from_daemon(self) -> None:
        try:
            pts = self.client.get("Curve")
        except Exception:
            return
        if not pts:
            return
        try:
            self.curve_model.points = [(float(t), int(l)) for t, l in pts]
        except (TypeError, ValueError):
            return
        refresh = getattr(self.curve_editor, "refresh", None)
        if callable(refresh):
            refresh()
