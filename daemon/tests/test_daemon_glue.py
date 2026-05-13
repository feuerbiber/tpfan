from __future__ import annotations
from pathlib import Path
import pytest
from tpfan_daemon.daemon import Daemon
from tpfan_daemon.config import load


class StubSensors:
    def __init__(self):
        self.temps = {"CPU": 50.0, "GPU": 50.0, "NVMe": 40.0}
    def read_all(self): return dict(self.temps)
    def describe(self): return {k: (v, k, k) for k, v in self.temps.items()}


class StubFan:
    def __init__(self): self.level = "auto"; self.history = []
    def writable(self): return True
    def read(self):
        class S: pass
        s = S(); s.level = self.level; s.speed_rpm = 2000; s.enabled = True
        return s
    def set_level(self, lvl): self.level = lvl; self.history.append(lvl)


def test_set_mode_persists(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    d = Daemon(config_path=cfg_path, sensors=StubSensors(), fan=StubFan())
    d.handle("set_mode", "manual")
    assert d.loop.config.mode == "manual"
    assert load(cfg_path).mode == "manual"


def test_set_curve_validates_and_persists(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    d = Daemon(config_path=cfg_path, sensors=StubSensors(), fan=StubFan())
    d.handle("set_curve", [(40.0, 0), (80.0, 7)], ["CPU"])
    assert d.loop.config.curve.points == ((40.0, 0), (80.0, 7))
    assert d.loop.config.curve.sensors == ("CPU",)


def test_set_curve_rejects_unknown_sensor(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    d = Daemon(config_path=cfg_path, sensors=StubSensors(), fan=StubFan())
    with pytest.raises(ValueError):
        d.handle("set_curve", [(40.0, 0), (80.0, 7)], ["DOES_NOT_EXIST"])


def test_set_manual_level_only_in_manual(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    d = Daemon(config_path=cfg_path, sensors=StubSensors(), fan=StubFan())
    with pytest.raises(ValueError):
        d.handle("set_manual_level", "5")
    d.handle("set_mode", "manual")
    d.handle("set_manual_level", "5")
    assert d.loop.config.manual_level == "5"
