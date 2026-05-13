from __future__ import annotations
from tpfan_gui.views.history import HistoryBuffer


def test_appends_and_truncates_to_window():
    h = HistoryBuffer(window_seconds=5)
    for t in range(10):
        h.append(float(t), {"CPU": float(40 + t)})
    xs, series = h.snapshot()
    assert 5 <= len(xs) <= 6
    assert series["CPU"][-1] == 49.0


def test_handles_missing_sensor_per_tick():
    h = HistoryBuffer(window_seconds=10)
    h.append(0.0, {"CPU": 40.0, "GPU": 50.0})
    h.append(1.0, {"CPU": 41.0})
    _, series = h.snapshot()
    assert series["CPU"] == [40.0, 41.0]
    assert series["GPU"] == [50.0]
