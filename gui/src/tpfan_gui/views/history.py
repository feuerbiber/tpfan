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
    from PyQt6.QtWidgets import QWidget, QVBoxLayout

    class HistoryWidget(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.buf = HistoryBuffer()
            lay = QVBoxLayout(self)
            self.plot = pg.PlotWidget()
            self.plot.setLabel("left", "°C")
            self.plot.setLabel("bottom", "Zeit (s)")
            self.plot.showGrid(x=True, y=True, alpha=0.25)
            self.legend = self.plot.addLegend(offset=(-10, 10),
                                              labelTextColor="w",
                                              brush=(40, 40, 40, 200))
            lay.addWidget(self.plot)
            self._curves: dict[str, pg.PlotDataItem] = {}

        def append(self, t: float, temps: dict[str, float]) -> None:
            self.buf.append(t, temps)
            per = self.buf.snapshot_per_series()
            all_t = [ts[0] for ts, _ in per.values() if ts]
            t0 = min(all_t) if all_t else 0.0
            for name, (xs, ys) in per.items():
                if name not in self._curves:
                    color = color_for_sensor(name, fallback_index=len(self._curves))
                    pen = pg.mkPen(color=QColor(color), width=2)
                    self._curves[name] = self.plot.plot(name=name, pen=pen)
                self._curves[name].setData([x - t0 for x in xs], ys)

    return HistoryWidget(parent)
