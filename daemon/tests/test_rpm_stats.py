from __future__ import annotations
from pathlib import Path
from tpfan_daemon.rpm_stats import RpmStatsTracker, load_stats, save_stats


def test_record_updates_last_min_max_count():
    t = RpmStatsTracker()
    t.record("3", 2400)
    t.record("3", 2800)
    t.record("3", 2600)
    d = t.as_dict()
    assert d["3"] == (2600, 2400, 2800, 3)


def test_record_ignores_invalid():
    t = RpmStatsTracker()
    t.record("", 1000)
    t.record("3", -1)
    assert t.as_dict() == {}


def test_reset_clears_all():
    t = RpmStatsTracker()
    t.record("3", 2500)
    t.reset()
    assert t.as_dict() == {}


def test_save_load_roundtrip(tmp_path: Path):
    t = RpmStatsTracker()
    t.record("3", 2700)
    t.record("3", 2900)
    t.record("7", 4900)
    p = tmp_path / "sub" / "rpm.json"
    save_stats(p, t)
    t2 = load_stats(p)
    assert t2.as_dict() == t.as_dict()


def test_load_missing_file_returns_empty(tmp_path: Path):
    t = load_stats(tmp_path / "nope.json")
    assert t.as_dict() == {}


def test_load_corrupt_returns_empty(tmp_path: Path):
    p = tmp_path / "rpm.json"
    p.write_text("{ not valid json")
    t = load_stats(p)
    assert t.as_dict() == {}
