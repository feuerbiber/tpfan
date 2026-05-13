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


def make_widget(parent=None):
    import pyqtgraph as pg
    from PyQt6.QtWidgets import QWidget, QVBoxLayout

    class HistoryWidget(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.buf = HistoryBuffer()
            lay = QVBoxLayout(self)
            self.plot = pg.PlotWidget()
            self.plot.setLabel("left", "°C")
            self.plot.setLabel("bottom", "Zeit (s)")
            self.plot.addLegend()
            lay.addWidget(self.plot)
            self._curves: dict[str, pg.PlotDataItem] = {}

        def append(self, t: float, temps: dict[str, float]) -> None:
            self.buf.append(t, temps)
            per = self.buf.snapshot_per_series()
            all_t = [ts[0] for ts, _ in per.values() if ts]
            t0 = min(all_t) if all_t else 0.0
            for name, (xs, ys) in per.items():
                if name not in self._curves:
                    self._curves[name] = self.plot.plot(name=name)
                self._curves[name].setData([x - t0 for x in xs], ys)

    return HistoryWidget(parent)
