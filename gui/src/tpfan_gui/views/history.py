from __future__ import annotations
from collections import deque
from dataclasses import dataclass


@dataclass
class HistoryBuffer:
    window_seconds: float = 600.0

    def __post_init__(self):
        self._t: deque[float] = deque()
        self._values: dict[str, deque[tuple[float, float]]] = {}

    def append(self, t: float, temps: dict[str, float]) -> None:
        self._t.append(t)
        for name, v in temps.items():
            self._values.setdefault(name, deque()).append((t, v))
        cutoff = t - self.window_seconds
        while self._t and self._t[0] < cutoff:
            self._t.popleft()
        for buf in self._values.values():
            while buf and buf[0][0] < cutoff:
                buf.popleft()

    def snapshot(self):
        xs = list(self._t)
        series = {name: [v for _, v in pts] for name, pts in self._values.items()}
        return xs, series

    def snapshot_per_series(self) -> dict[str, tuple[list[float], list[float]]]:
        return {
            name: ([t for t, _ in pts], [v for _, v in pts])
            for name, pts in self._values.items()
        }


SENSOR_COLORS: dict[str, str] = {
    "CPU":    "#e6194b",
    "GPU":    "#3cb44b",
    "NVMe":   "#4363d8",
    "RAM":    "#f58231",
    "WLAN":   "#911eb4",
    "MB-CPU": "#46f0f0",
    "MB-GPU": "#f032e6",
    "ACPI":   "#bcf60c",
}
FALLBACK_PALETTE = ["#fabebe", "#008080", "#e6beff", "#9a6324", "#fffac8",
                    "#800000", "#aaffc3", "#808000", "#ffd8b1", "#000075"]


def color_for_sensor(name: str, fallback_index: int = 0) -> str:
    if name in SENSOR_COLORS:
        return SENSOR_COLORS[name]
    return FALLBACK_PALETTE[fallback_index % len(FALLBACK_PALETTE)]


def make_widget(parent=None):
    import pyqtgraph as pg
    from PyQt6.QtGui import QColor
    from PyQt6.QtCore import QEvent, QObject, QSettings
    from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QCheckBox,
                                  QFrame)

    NORMAL_WIDTH = 2
    HOVER_WIDTH = 4

    class HistoryWidget(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.buf = HistoryBuffer()
            lay = QVBoxLayout(self)
            self.plot = pg.PlotWidget()
            self.plot.setLabel("left", "°C")
            self.plot.setLabel("bottom", "Zeit (s)")
            self.plot.showGrid(x=True, y=True, alpha=0.25)
            self.legend = self.plot.addLegend(offset=(10, 10),
                                              labelTextColor="w",
                                              brush=(40, 40, 40, 200))
            lay.addWidget(self.plot)

            # Checkbox-Gitter: pro Sensor eine Box zum Ausblenden der Kurve,
            # auf zwei Zeilen verteilt (kein horizontales Scrollen).
            self._toggle_host = QFrame()
            self._toggle_grid = QGridLayout(self._toggle_host)
            self._toggle_grid.setContentsMargins(4, 2, 4, 2)
            self._toggle_grid.setHorizontalSpacing(12)
            self._toggle_grid.setVerticalSpacing(2)
            lay.addWidget(self._toggle_host)

            self._curves: dict[str, pg.PlotDataItem] = {}
            self._toggles: dict[str, QCheckBox] = {}
            self._colors: dict[str, str] = {}
            self._cb_to_name: dict[QObject, str] = {}
            self._settings = QSettings()

        def _visibility_key(self, name: str) -> str:
            return f"history/visible/{name}"

        def _load_visibility(self, name: str) -> bool:
            # QSettings liefert je nach Plattform/Backend evtl. "true"/"false"
            # statt bool zurück — robust per `type=bool` parsen.
            return self._settings.value(self._visibility_key(name), True, type=bool)

        def _add_toggle(self, name: str, color: str) -> None:
            visible = self._load_visibility(name)
            cb = QCheckBox(name)
            cb.setChecked(visible)
            cb.setStyleSheet(f"QCheckBox {{ color: {color}; }}")
            cb.toggled.connect(lambda checked, n=name: self._set_curve_visible(n, checked))
            cb.setAttribute(pg.QtCore.Qt.WidgetAttribute.WA_Hover, True)
            cb.installEventFilter(self)
            self._cb_to_name[cb] = name
            # Verteilung auf 2 Zeilen: gerade Indizes oben, ungerade unten.
            # Spalten werden links bündig aufgefüllt.
            idx = len(self._toggles)
            row = idx % 2
            col = idx // 2
            self._toggle_grid.addWidget(cb, row, col)
            self._toggles[name] = cb
            self._colors[name] = color
            # Anfangszustand auf die Kurve anwenden, ohne erneut zu schreiben.
            if not visible:
                self._curves[name].setVisible(False)
                try:
                    self.legend.removeItem(name)
                except Exception:
                    pass

        def eventFilter(self, obj, ev):
            t = ev.type()
            if t == QEvent.Type.Enter:
                name = self._cb_to_name.get(obj)
                if name is not None:
                    self._set_curve_width(name, HOVER_WIDTH)
            elif t == QEvent.Type.Leave:
                name = self._cb_to_name.get(obj)
                if name is not None:
                    self._set_curve_width(name, NORMAL_WIDTH)
            return super().eventFilter(obj, ev)

        def _set_curve_width(self, name: str, width: int) -> None:
            curve = self._curves.get(name)
            color = self._colors.get(name)
            if curve is None or color is None:
                return
            curve.setPen(pg.mkPen(color=QColor(color), width=width))

        def _set_curve_visible(self, name: str, visible: bool) -> None:
            curve = self._curves.get(name)
            if curve is None:
                return
            curve.setVisible(visible)
            self._settings.setValue(self._visibility_key(name), bool(visible))
            # Legenden-Eintrag mitschalten, damit die Legende nicht
            # ausgeblendete Kurven weiter anpreist.
            try:
                self.legend.removeItem(name)
                if visible:
                    self.legend.addItem(curve, name)
            except Exception:
                pass

        def append(self, t: float, temps: dict[str, float]) -> None:
            self.buf.append(t, temps)
            per = self.buf.snapshot_per_series()
            all_t = [ts[0] for ts, _ in per.values() if ts]
            t0 = min(all_t) if all_t else 0.0
            for name, (xs, ys) in per.items():
                if name not in self._curves:
                    color = color_for_sensor(name, fallback_index=len(self._curves))
                    pen = pg.mkPen(color=QColor(color), width=NORMAL_WIDTH)
                    self._curves[name] = self.plot.plot(name=name, pen=pen)
                    self._add_toggle(name, color)
                self._curves[name].setData([x - t0 for x in xs], ys)

    return HistoryWidget(parent)
