from __future__ import annotations
from pathlib import Path
import pytest
from tpfan_daemon.hw.sensors import Sensors
from .conftest import make_hwmon


def test_discovery_maps_known_drivers(hwmon_tree: Path):
    make_hwmon(hwmon_tree, 0, "k10temp",   temps={"temp1": 45.0}, labels={"temp1": "Tctl"})
    make_hwmon(hwmon_tree, 1, "amdgpu",    temps={"temp1": 50.0}, labels={"temp1": "edge"})
    make_hwmon(hwmon_tree, 2, "nvme",      temps={"temp1": 38.0, "temp2": 40.0}, labels={"temp1": "Composite"})
    make_hwmon(hwmon_tree, 3, "thinkpad",  temps={"temp1": 47.0, "temp2": 48.0}, labels={"temp1": "CPU", "temp2": "GPU"})

    s = Sensors(root=hwmon_tree)
    s.discover()
    readings = s.read_all()

    assert readings["CPU"] == pytest.approx(45.0)
    assert readings["GPU"] == pytest.approx(50.0)
    assert readings["NVMe"] == pytest.approx(38.0)
    assert readings["MB-CPU"] == pytest.approx(47.0)
    assert readings["MB-GPU"] == pytest.approx(48.0)


def test_unreadable_sensor_skipped(hwmon_tree: Path):
    d = make_hwmon(hwmon_tree, 0, "k10temp", temps={"temp1": 45.0}, labels={"temp1": "Tctl"})
    (d / "temp2_input").write_text("garbage\n")
    (d / "temp2_label").write_text("Tctl\n")
    s = Sensors(root=hwmon_tree); s.discover()
    r = s.read_all()
    assert r == {"CPU": pytest.approx(45.0)}


def test_unknown_driver_exposed_generically(hwmon_tree: Path):
    make_hwmon(hwmon_tree, 0, "exotic_driver",
               temps={"temp1": 30.0, "temp2": 31.0},
               labels={"temp1": "zone_a"})
    s = Sensors(root=hwmon_tree); s.discover()
    r = s.read_all()
    assert r["exotic_driver-zone_a"] == pytest.approx(30.0)
    assert r["exotic_driver-temp2"] == pytest.approx(31.0)


def test_generic_name_collision_disambiguated(hwmon_tree: Path):
    # zwei hwmon-Instanzen mit identischem Treibernamen und ohne Label →
    # zweiter bekommt Suffix '#2', damit der Schlüssel eindeutig bleibt.
    make_hwmon(hwmon_tree, 0, "iwlwifi_1", temps={"temp1": 40.0})
    make_hwmon(hwmon_tree, 1, "iwlwifi_1", temps={"temp1": 41.0})
    s = Sensors(root=hwmon_tree); s.discover()
    r = s.read_all()
    assert r["iwlwifi_1-temp1"] == pytest.approx(40.0)
    assert r["iwlwifi_1-temp1#2"] == pytest.approx(41.0)


def test_coretemp_maps_to_cpu(hwmon_tree: Path):
    make_hwmon(hwmon_tree, 0, "coretemp",
               temps={"temp1": 52.0, "temp2": 51.0, "temp3": 50.0},
               labels={"temp1": "Package id 0", "temp2": "Core 0", "temp3": "Core 1"})
    s = Sensors(root=hwmon_tree); s.discover()
    r = s.read_all()
    assert r["CPU"] == pytest.approx(52.0)
    # Cores fallen auf generischen Namen zurück, damit sie nicht verloren gehen.
    assert r["coretemp-Core 0"] == pytest.approx(51.0)
    assert r["coretemp-Core 1"] == pytest.approx(50.0)


def test_thinkpad_generic_zone_indexed(hwmon_tree: Path):
    make_hwmon(hwmon_tree, 0, "thinkpad",
               temps={"temp3": 40.0, "temp4": 41.0},
               labels={"temp3": "other", "temp4": "other2"})
    s = Sensors(root=hwmon_tree); s.discover()
    r = s.read_all()
    assert r["MB-temp3"] == pytest.approx(40.0)
    assert r["MB-temp4"] == pytest.approx(41.0)
