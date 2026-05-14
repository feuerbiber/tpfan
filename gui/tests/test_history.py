from __future__ import annotations
from tpfan_gui.views.history import HistoryBuffer, SENSOR_COLORS, color_for_sensor


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


def test_color_for_sensor_known_and_fallback():
    assert color_for_sensor("CPU") == SENSOR_COLORS["CPU"]
    assert color_for_sensor("GPU") == SENSOR_COLORS["GPU"]
    c1 = color_for_sensor("Custom1", fallback_index=0)
    c2 = color_for_sensor("Custom2", fallback_index=1)
    assert c1 != c2
    assert c1.startswith("#") and c2.startswith("#")


def test_snapshot_per_series_handles_gaps():
    h = HistoryBuffer(window_seconds=60)
    h.append(0.0, {"CPU": 40.0, "GPU": 50.0})
    h.append(1.0, {"CPU": 41.0})
    h.append(2.0, {"CPU": 42.0, "GPU": 52.0})
    per = h.snapshot_per_series()
    assert per["CPU"] == ([0.0, 1.0, 2.0], [40.0, 41.0, 42.0])
    assert per["GPU"] == ([0.0, 2.0], [50.0, 52.0])
