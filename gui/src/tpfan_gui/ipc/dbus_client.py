from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import logging

log = logging.getLogger(__name__)

BUS_NAME = "org.tpfan1"
OBJECT_PATH = "/org/tpfan1"


@dataclass(frozen=True)
class TickPayload:
    temps: dict[str, float]
    fans: list[tuple[int, str]]
    level: str


def _level_int_to_str(n: int) -> str:
    if n == 0xFF:
        return "auto"
    if n == 0xFE:
        return "disengaged"
    if 0 <= n <= 7:
        return str(n)
    return "unknown"


class DaemonNotConnected(RuntimeError):
    """Raised when a write call is attempted while the D-Bus proxy is unavailable."""


class _ProxyOps:
    """Mixin: kapselt Proxy-Zugriff und Schreib-Methoden.

    Auf Modul-Ebene definiert (statt im make_client-Closure), damit die
    set_*/reload_config-Verträge ohne PyQt6/D-Bus unit-getestet werden können.
    Erwartet self._proxy als Attribut (initial None).
    """

    def _require_proxy(self):
        proxy = getattr(self, "_proxy", None)
        if proxy is None:
            raise DaemonNotConnected("daemon not reachable")
        return proxy

    def get(self, name: str):
        proxy = getattr(self, "_proxy", None)
        if proxy is None:
            return None
        return getattr(proxy, name)

    def set_mode(self, mode: str): self._require_proxy().SetMode(mode)
    def set_curve(self, points, sensors): self._require_proxy().SetCurve(points, sensors)
    def set_manual_level(self, lvl: str): self._require_proxy().SetManualLevel(lvl)
    def set_failsafe_temp(self, t: float): self._require_proxy().SetFailsafeTemp(t)
    def reload_config(self): self._require_proxy().ReloadConfig()
    def reset_rpm_stats(self): self._require_proxy().ResetLevelRpmStats()


def translate_tick(temps: dict[str, float],
                   fans_raw: list[tuple[int, int]],
                   level: str) -> TickPayload:
    return TickPayload(
        temps=dict(temps),
        fans=[(int(rpm), _level_int_to_str(int(lvl))) for rpm, lvl in fans_raw],
        level=str(level),
    )


def make_client(parent=None):
    """Lazy-Erstellung des Qt+D-Bus-Clients (PyQt6 nur hier importieren,
    damit Logik-Tests headless laufen)."""
    from PyQt6.QtCore import QObject, pyqtSignal, QTimer
    from dasbus.connection import SystemMessageBus
    from dasbus.error import DBusError

    class Client(_ProxyOps, QObject):
        tickReceived = pyqtSignal(object)
        propertiesChanged = pyqtSignal(dict)
        emergency = pyqtSignal(float, str)
        connected = pyqtSignal(bool)

        def __init__(self, parent=None):
            super().__init__(parent)
            self._bus: Optional[SystemMessageBus] = None
            self._proxy = None
            self._connected = False
            self._reconnect = QTimer(self)
            self._reconnect.setInterval(2000)
            self._reconnect.timeout.connect(self._try_connect)
            self._reconnect.start()
            self._try_connect()

        def _try_connect(self):
            # Bereits verbunden -> kein Re-Subscribe (würde Slots duplizieren).
            if self._connected:
                return
            try:
                if self._bus is None:
                    self._bus = SystemMessageBus()
                proxy = self._bus.get_proxy(BUS_NAME, OBJECT_PATH)
                proxy.Tick.connect(self._on_tick)
                proxy.EmergencyTriggered.connect(self._on_emergency)
                proxy.PropertiesChanged.connect(self._on_props)
                # Erfolg: erst jetzt State setzen, Timer stoppen, Signal emittieren.
                self._proxy = proxy
                self._connected = True
                self._reconnect.stop()
                self.connected.emit(True)
            except DBusError as e:
                log.warning("daemon not reachable: %s", e)
                self._proxy = None
                self._connected = False
                self.connected.emit(False)

        def _on_tick(self, temps, fans, level):
            self.tickReceived.emit(translate_tick(temps, fans, level))

        def _on_emergency(self, temp, sensor):
            self.emergency.emit(float(temp), str(sensor))

        def _on_props(self, iface, changed, invalidated):
            self.propertiesChanged.emit(dict(changed))

    return Client(parent)
