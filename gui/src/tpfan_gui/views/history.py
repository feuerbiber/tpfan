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
            xs, series = self.buf.snapshot()
            t0 = xs[0] if xs else 0.0
            xs_rel = [x - t0 for x in xs]
            for name, ys in series.items():
                if name not in self._curves:
                    self._curves[name] = self.plot.plot(name=name)
                self._curves[name].setData(xs_rel[-len(ys):], ys)

    return HistoryWidget(parent)
