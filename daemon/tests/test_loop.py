from __future__ import annotations
from dataclasses import dataclass
from tpfan_daemon.control.loop import ControlLoop
from tpfan_daemon.config import Config, CurveCfg, DEFAULT


class FakeSensors:
    def __init__(self, temps):
        self.temps = temps
        self.fail_read: bool = False
    def read_all(self):
        if self.fail_read:
            raise OSError("sensors unavailable")
        return dict(self.temps)


class FakeFan:
    def __init__(self):
        self.level = "auto"
        self.history: list[str] = []
        self.fail_set: bool = False
        self.fail_read: bool = False
        self.fail_only_non_auto: bool = False

    def read(self):
        if self.fail_read:
            raise OSError("fan read failed")
        @dataclass
        class S:
            speed_rpm: int = 2000
            level: str = "auto"
            enabled: bool = True
        s = S()
        s.level = self.level
        return s

    def set_level(self, lvl):
        if self.fail_set and not (self.fail_only_non_auto and lvl == "auto"):
            raise OSError("nope")
        self.level = lvl
        self.history.append(lvl)


def _loop(temps, cfg=DEFAULT, fan=None):
    fan = fan or FakeFan()
    return ControlLoop(sensors=FakeSensors(temps), fan=fan, config=cfg), fan


def test_auto_mode_sets_auto():
    loop, fan = _loop({"CPU": 50.0}, cfg=Config(mode="auto"))
    loop.tick()
    assert fan.level == "auto"


def test_manual_mode_sets_level():
    cfg = Config(mode="manual", manual_level="5")
    loop, fan = _loop({"CPU": 50.0}, cfg=cfg)
    loop.tick()
    assert fan.level == "5"


def test_curve_mode_uses_max_of_sensors():
    cfg = Config(mode="curve", curve=CurveCfg(("CPU","GPU"), ((40.0,0),(80.0,7))))
    loop, fan = _loop({"CPU": 40.0, "GPU": 80.0}, cfg=cfg)
    loop.tick()
    assert fan.level == "7"


def test_failsafe_disengages_above_threshold():
    cfg = Config(mode="curve", failsafe_temp=70.0,
                 curve=CurveCfg(("CPU",), ((40.0,0),(80.0,7))))
    loop, fan = _loop({"CPU": 75.0}, cfg=cfg)
    tr = loop.tick()
    assert fan.level == "disengaged"
    assert tr.emergency is not None
    assert tr.emergency[1] == "CPU"


def test_curve_unchanged_level_does_not_rewrite():
    cfg = Config(mode="curve", curve=CurveCfg(("CPU",), ((40.0,0),(80.0,7))))
    loop, fan = _loop({"CPU": 80.0}, cfg=cfg)
    loop.tick()
    n = len(fan.history)
    loop.tick()
    assert len(fan.history) == n


def test_fan_write_failure_falls_back_to_auto():
    cfg = Config(mode="manual", manual_level="5")
    fan = FakeFan()
    fan.fail_set = True
    loop, _ = _loop({"CPU": 50.0}, cfg=cfg, fan=fan)
    tr = loop.tick()
    assert tr.fallback_to_auto is True


def test_profile_mode_uses_profile_curve():
    cfg = Config(mode="profile:quiet", profiles=DEFAULT.profiles)
    loop, fan = _loop({"CPU": 85.0}, cfg=cfg)
    loop.tick()
    assert fan.level == "7"


def test_failsafe_write_failure_falls_back_to_auto():
    cfg = Config(mode="curve", failsafe_temp=70.0,
                 curve=CurveCfg(("CPU",), ((40.0, 0), (80.0, 7))))
    fan = FakeFan()
    fan.fail_set = True
    fan.fail_only_non_auto = True
    loop, _ = _loop({"CPU": 95.0}, cfg=cfg, fan=fan)
    tr = loop.tick()
    assert tr.emergency is not None
    assert tr.fallback_to_auto is True


def test_set_config_resets_curve_state_on_mode_change():
    curve = CurveCfg(("CPU",), ((40.0, 0), (80.0, 7)))
    cfg_curve = Config(mode="curve", curve=curve)
    loop, fan = _loop({"CPU": 80.0}, cfg=cfg_curve)
    loop.tick()
    assert loop._last_curve_level == 7
    loop.set_config(Config(mode="manual", manual_level="3"))
    assert loop._last_curve_level == 0
    loop.set_config(cfg_curve)
    assert loop._last_curve_level == 0
    loop.sensors.temps = {"CPU": 42.0}
    loop.tick()
    assert loop._last_curve_level < 7


def test_sensors_read_failure_falls_back_to_auto():
    cfg = Config(mode="manual", manual_level="5")
    fan = FakeFan()
    sensors = FakeSensors({"CPU": 50.0})
    sensors.fail_read = True
    loop = ControlLoop(sensors=sensors, fan=fan, config=cfg)
    tr = loop.tick()
    assert tr.fallback_to_auto is True
    assert tr.temps == {}
    assert tr.target_level == "auto"


def test_last_level_property():
    cfg = Config(mode="manual", manual_level="5")
    loop, _ = _loop({"CPU": 50.0}, cfg=cfg)
    loop.tick()
    assert loop.last_level == "5"


def test_fan_read_failure_falls_back_to_auto():
    cfg = Config(mode="manual", manual_level="5")
    fan = FakeFan()
    fan.fail_read = True
    loop, _ = _loop({"CPU": 50.0}, cfg=cfg, fan=fan)
    tr = loop.tick()
    assert tr.fallback_to_auto is True
    assert tr.target_level == "auto"
