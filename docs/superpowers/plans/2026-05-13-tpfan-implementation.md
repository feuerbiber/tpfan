# tpfan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lüfter-Steuerung und Temperatur-Anzeige für ThinkPad E14 Gen 7 unter Linux — als root-Daemon mit D-Bus-API und PyQt6-GUI, inkl. benutzerdefinierter Lüfterkurve, Profilen, Failsafe und Live-Verlauf.

**Architecture:** Trennung in zwei Python-Pakete: `tpfan-daemon` läuft als systemd-Unit (root) und kapselt `/sys/class/hwmon` + `/proc/acpi/ibm/fan` hinter einer 1-Hz-Regelschleife mit Hysterese und Failsafe; `tpfan-gui` ist reiner D-Bus-Client (User-Session). Schreibende D-Bus-Methoden sind PolicyKit-geschützt; Konfiguration in `/etc/tpfan/config.toml` mit atomic write.

**Tech Stack:** Python ≥ 3.11, `dasbus` (D-Bus), `tomllib` (stdlib), `PyQt6`, `pyqtgraph`, `pytest`, systemd, polkit, `thinkpad_acpi` (mit `fan_control=1`).

**Konventionen:**
- TDD: Test zuerst, fehlschlagen lassen, minimal implementieren, grün stellen, committen.
- Commits sind klein und sprachlich präzise (`feat:`, `fix:`, `test:`, `refactor:`, `docs:`, `chore:`).
- Pfade in diesem Plan sind relativ zum Repo-Root `tpfan/` (aktuell `/home/matthias/programmieren/tmp-fan/`).
- Alle Tests werden mit `pytest -q` ausgeführt, sofern nicht anders angegeben.

---

## Phase 0 — Projekt-Setup

### Task 0.1: Top-Level-Layout und Makefile

**Files:**
- Create: `Makefile`
- Create: `README.md`
- Create: `.gitignore`

- [ ] **Step 1: `.gitignore` anlegen**

```gitignore
__pycache__/
*.pyc
.pytest_cache/
.coverage
htmlcov/
*.egg-info/
dist/
build/
.venv/
```

- [ ] **Step 2: Minimales `README.md` anlegen**

```markdown
# tpfan

Lüfter-Steuerung und Temperatur-Anzeige für ThinkPad E14 Gen 7 unter Linux.

Siehe `docs/superpowers/specs/2026-05-10-tpfan-design.md`.

## Installation (Entwickler)

    make dev      # editable installs für daemon + gui in .venv
    make test     # alle Unit-Tests
    make install  # System-Installation (sudo)
```

- [ ] **Step 3: `Makefile` mit Phony-Targets anlegen**

```makefile
.PHONY: dev test test-daemon test-gui install uninstall clean

VENV ?= .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

dev: $(VENV)/bin/activate
	$(PIP) install -e ./daemon[dev]
	$(PIP) install -e ./gui[dev]

test: test-daemon test-gui

test-daemon:
	$(PY) -m pytest daemon/tests -q

test-gui:
	$(PY) -m pytest gui/tests -q

install:
	install -D -m 0755 packaging/tpfan-daemon-launcher /usr/local/bin/tpfan-daemon
	install -D -m 0755 packaging/tpfan-gui-launcher    /usr/local/bin/tpfan-gui
	install -D -m 0644 packaging/tpfan-daemon.service  /etc/systemd/system/tpfan-daemon.service
	install -D -m 0644 packaging/org.tpfan1.conf       /etc/dbus-1/system.d/org.tpfan1.conf
	install -D -m 0644 packaging/org.tpfan1.service    /usr/share/dbus-1/system-services/org.tpfan1.service
	install -D -m 0644 packaging/org.tpfan1.policy     /usr/share/polkit-1/actions/org.tpfan1.policy
	install -D -m 0644 packaging/tpfan-modprobe.conf   /etc/modprobe.d/tpfan.conf
	install -D -m 0644 packaging/tpfan-gui.desktop     /usr/share/applications/tpfan-gui.desktop
	systemctl daemon-reload

uninstall:
	rm -f /usr/local/bin/tpfan-daemon /usr/local/bin/tpfan-gui
	rm -f /etc/systemd/system/tpfan-daemon.service
	rm -f /etc/dbus-1/system.d/org.tpfan1.conf
	rm -f /usr/share/dbus-1/system-services/org.tpfan1.service
	rm -f /usr/share/polkit-1/actions/org.tpfan1.policy
	rm -f /etc/modprobe.d/tpfan.conf
	rm -f /usr/share/applications/tpfan-gui.desktop
	systemctl daemon-reload

clean:
	rm -rf $(VENV) .pytest_cache **/*.egg-info
```

- [ ] **Step 4: Commit**

```bash
git add Makefile README.md .gitignore
git commit -m "chore: add top-level Makefile, README, gitignore"
```

### Task 0.2: Daemon-Paket-Skelett

**Files:**
- Create: `daemon/pyproject.toml`
- Create: `daemon/src/tpfan_daemon/__init__.py`
- Create: `daemon/tests/__init__.py`
- Create: `daemon/tests/conftest.py`

- [ ] **Step 1: `daemon/pyproject.toml` anlegen**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "tpfan-daemon"
version = "0.1.0"
description = "ThinkPad fan control daemon"
requires-python = ">=3.11"
dependencies = ["dasbus>=1.7"]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-cov>=5"]

[project.scripts]
tpfan-daemon = "tpfan_daemon.__main__:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"
```

- [ ] **Step 2: Leere Init-Module anlegen**

```python
# daemon/src/tpfan_daemon/__init__.py
__version__ = "0.1.0"
```

```python
# daemon/tests/__init__.py
```

- [ ] **Step 3: `conftest.py` für hwmon-Fixtures anlegen**

```python
# daemon/tests/conftest.py
from __future__ import annotations
from pathlib import Path
import pytest


@pytest.fixture
def hwmon_tree(tmp_path: Path) -> Path:
    """Fake /sys/class/hwmon Baum. Tests füllen Dateien selbst."""
    root = tmp_path / "hwmon"
    root.mkdir()
    return root


def make_hwmon(root: Path, idx: int, name: str, temps: dict[str, float] | None = None,
               fans: dict[str, int] | None = None, labels: dict[str, str] | None = None) -> Path:
    """Erzeugt hwmon{idx}/ mit name + temp*_input/_label, fan*_input.

    temps: {"temp1": 42.0, ...} → millicelsius in temp1_input
    fans:  {"fan1": 2800, ...}
    labels: {"temp1": "Tctl", ...}
    """
    d = root / f"hwmon{idx}"
    d.mkdir()
    (d / "name").write_text(name + "\n")
    for k, v in (temps or {}).items():
        (d / f"{k}_input").write_text(f"{int(v * 1000)}\n")
    for k, v in (labels or {}).items():
        (d / f"{k}_label").write_text(v + "\n")
    for k, v in (fans or {}).items():
        (d / f"{k}_input").write_text(f"{v}\n")
    return d
```

- [ ] **Step 4: Commit**

```bash
git add daemon/
git commit -m "chore(daemon): add package skeleton and hwmon test fixtures"
```

### Task 0.3: GUI-Paket-Skelett

**Files:**
- Create: `gui/pyproject.toml`
- Create: `gui/src/tpfan_gui/__init__.py`
- Create: `gui/tests/__init__.py`

- [ ] **Step 1: `gui/pyproject.toml` anlegen**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "tpfan-gui"
version = "0.1.0"
description = "ThinkPad fan control GUI"
requires-python = ">=3.11"
dependencies = ["PyQt6>=6.6", "pyqtgraph>=0.13", "dasbus>=1.7"]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-qt>=4.4"]

[project.scripts]
tpfan-gui = "tpfan_gui.__main__:main"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 2: Leere Init-Module anlegen**

```python
# gui/src/tpfan_gui/__init__.py
__version__ = "0.1.0"
```

```python
# gui/tests/__init__.py
```

- [ ] **Step 3: Commit**

```bash
git add gui/
git commit -m "chore(gui): add package skeleton"
```

---

## Phase 1 — Daemon: HW-Abstraktion

### Task 1.1: `hw/sensors.py` — Discovery und semantisches Mapping

**Files:**
- Create: `daemon/src/tpfan_daemon/hw/__init__.py`
- Create: `daemon/src/tpfan_daemon/hw/sensors.py`
- Create: `daemon/tests/test_sensors.py`

Modul-Verantwortung: hwmon-Discovery, Mapping der Treibernamen (`k10temp`, `amdgpu`, `nvme`, `thinkpad`, `spd5118`, `mt7921_phy0`, `acpitz`) auf semantische Sensor-Namen (CPU, GPU, NVMe, RAM, WLAN, MB-*, ACPI), fehlertolerantes Lesen.

- [ ] **Step 1: Test schreiben — Discovery erkennt alle Treiber**

```python
# daemon/tests/test_sensors.py
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
```

- [ ] **Step 2: Test laufen lassen — erwartet FAIL**

Run: `.venv/bin/python -m pytest daemon/tests/test_sensors.py -q`
Expected: FAIL mit `ModuleNotFoundError: tpfan_daemon.hw`

- [ ] **Step 3: Modul implementieren**

```python
# daemon/src/tpfan_daemon/hw/__init__.py
```

```python
# daemon/src/tpfan_daemon/hw/sensors.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import logging

log = logging.getLogger(__name__)

# Mapping: (hwmon-name, label-substring or None) -> semantischer Name.
# Reihenfolge bestimmt Prioritaet bei doppelten Hits.
_MAP: list[tuple[str, str | None, str]] = [
    ("k10temp",     "Tctl",      "CPU"),
    ("amdgpu",      "edge",      "GPU"),
    ("nvme",        "Composite", "NVMe"),
    ("nvme",        "Sensor 1",  "NVMe-S1"),
    ("nvme",        "Sensor 2",  "NVMe-S2"),
    ("thinkpad",    "CPU",       "MB-CPU"),
    ("thinkpad",    "GPU",       "MB-GPU"),
    ("thinkpad",    None,        "MB"),
    ("spd5118",     None,        "RAM"),
    ("mt7921_phy0", None,        "WLAN"),
    ("acpitz",      None,        "ACPI"),
]


@dataclass(frozen=True)
class SensorRef:
    name: str
    path: Path
    source: str


@dataclass
class Sensors:
    root: Path = Path("/sys/class/hwmon")
    refs: list[SensorRef] = field(default_factory=list)

    def discover(self) -> None:
        self.refs = []
        for d in sorted(self.root.iterdir()):
            if not d.is_dir():
                continue
            name_file = d / "name"
            if not name_file.exists():
                continue
            try:
                drv = name_file.read_text().strip()
            except OSError:
                continue
            for input_path in sorted(d.glob("temp*_input")):
                idx = input_path.name[len("temp"):-len("_input")]
                label_path = d / f"temp{idx}_label"
                label = label_path.read_text().strip() if label_path.exists() else None
                sem = self._classify(drv, label, idx)
                if sem is None:
                    continue
                src = f"{drv}/{label or f'temp{idx}'}"
                self.refs.append(SensorRef(sem, input_path, src))

    def _classify(self, drv: str, label: str | None, idx: str) -> str | None:
        for d, lbl, sem in _MAP:
            if d != drv:
                continue
            if lbl is None:
                if drv == "thinkpad":
                    return f"MB-temp{idx}"
                return sem
            if label and lbl in label:
                return sem
        return None

    def read_all(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for r in self.refs:
            try:
                raw = r.path.read_text().strip()
                out[r.name] = int(raw) / 1000.0
            except (OSError, ValueError) as e:
                log.warning("sensor %s unreadable: %s", r.name, e)
        return out

    def describe(self) -> dict[str, tuple[float, str, str]]:
        out: dict[str, tuple[float, str, str]] = {}
        for r in self.refs:
            try:
                v = int(r.path.read_text().strip()) / 1000.0
            except (OSError, ValueError):
                continue
            out[r.name] = (v, r.name, r.source)
        return out
```

- [ ] **Step 4: Test laufen lassen — erwartet PASS**

Run: `.venv/bin/python -m pytest daemon/tests/test_sensors.py -q`
Expected: PASS

- [ ] **Step 5: Zusätzliche Robustheits-Tests anhängen**

```python
# in daemon/tests/test_sensors.py ergänzen:

def test_unreadable_sensor_skipped(hwmon_tree: Path):
    d = make_hwmon(hwmon_tree, 0, "k10temp", temps={"temp1": 45.0}, labels={"temp1": "Tctl"})
    (d / "temp2_input").write_text("garbage\n")
    (d / "temp2_label").write_text("Tctl\n")
    s = Sensors(root=hwmon_tree); s.discover()
    r = s.read_all()
    assert r == {"CPU": pytest.approx(45.0)}


def test_unknown_driver_ignored(hwmon_tree: Path):
    make_hwmon(hwmon_tree, 0, "exotic_driver", temps={"temp1": 30.0})
    s = Sensors(root=hwmon_tree); s.discover()
    assert s.read_all() == {}


def test_thinkpad_generic_zone_indexed(hwmon_tree: Path):
    make_hwmon(hwmon_tree, 0, "thinkpad",
               temps={"temp3": 40.0, "temp4": 41.0},
               labels={"temp3": "other", "temp4": "other2"})
    s = Sensors(root=hwmon_tree); s.discover()
    r = s.read_all()
    assert r["MB-temp3"] == pytest.approx(40.0)
    assert r["MB-temp4"] == pytest.approx(41.0)
```

- [ ] **Step 6: Tests laufen lassen — erwartet PASS**

Run: `.venv/bin/python -m pytest daemon/tests/test_sensors.py -q`
Expected: 4 passed

- [ ] **Step 7: Commit**

```bash
git add daemon/src/tpfan_daemon/hw daemon/tests/test_sensors.py
git commit -m "feat(daemon): hwmon discovery and semantic sensor mapping"
```

### Task 1.2: `hw/fan.py` — Wrapper um `/proc/acpi/ibm/fan`

**Files:**
- Create: `daemon/src/tpfan_daemon/hw/fan.py`
- Create: `daemon/tests/test_fan.py`

`/proc/acpi/ibm/fan` Format (Lesen):
```
status:         enabled
speed:          2754
level:          auto
commands:       level <level> (<level> is 0-7, auto, disengaged, full-speed)
```

Schreiben: `echo "level 3" > /proc/acpi/ibm/fan`.

- [ ] **Step 1: Test schreiben**

```python
# daemon/tests/test_fan.py
from __future__ import annotations
from pathlib import Path
import pytest
from tpfan_daemon.hw.fan import Fan, FanState


FAKE_PROC = """status:\t\tenabled
speed:\t\t2754
level:\t\tauto
commands:\tlevel <level> (<level> is 0-7, auto, disengaged, full-speed)
"""


def _write_fan(tmp: Path, content: str) -> Path:
    p = tmp / "fan"
    p.write_text(content)
    return p


def test_read_state(tmp_path: Path):
    p = _write_fan(tmp_path, FAKE_PROC)
    fan = Fan(path=p)
    st = fan.read()
    assert st == FanState(speed_rpm=2754, level="auto", enabled=True)


def test_set_level_writes_command(tmp_path: Path):
    p = _write_fan(tmp_path, FAKE_PROC)
    written: list[str] = []
    fan = Fan(path=p, _writer=lambda s: written.append(s))
    fan.set_level("3")
    assert written == ["level 3"]


def test_set_level_rejects_invalid(tmp_path: Path):
    p = _write_fan(tmp_path, FAKE_PROC)
    fan = Fan(path=p, _writer=lambda s: None)
    with pytest.raises(ValueError):
        fan.set_level("99")
    with pytest.raises(ValueError):
        fan.set_level("full-speed")


def test_set_level_retries_on_oserror(tmp_path: Path):
    p = _write_fan(tmp_path, FAKE_PROC)
    calls = {"n": 0}

    def flaky(s: str) -> None:
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("EBUSY")

    fan = Fan(path=p, _writer=flaky, _sleep=lambda _: None)
    fan.set_level("2")
    assert calls["n"] == 3


def test_set_level_gives_up_after_three(tmp_path: Path):
    p = _write_fan(tmp_path, FAKE_PROC)

    def always_fail(s: str) -> None:
        raise OSError("EBUSY")

    fan = Fan(path=p, _writer=always_fail, _sleep=lambda _: None)
    with pytest.raises(OSError):
        fan.set_level("2")
```

- [ ] **Step 2: Test laufen lassen — erwartet FAIL**

Run: `.venv/bin/python -m pytest daemon/tests/test_fan.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: `hw/fan.py` implementieren**

```python
# daemon/src/tpfan_daemon/hw/fan.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import time
import logging

log = logging.getLogger(__name__)

VALID_LEVELS = {"0", "1", "2", "3", "4", "5", "6", "7", "auto", "disengaged"}


@dataclass(frozen=True)
class FanState:
    speed_rpm: int
    level: str
    enabled: bool


@dataclass
class Fan:
    path: Path = Path("/proc/acpi/ibm/fan")
    _writer: Callable[[str], None] | None = None
    _sleep: Callable[[float], None] = time.sleep
    retries: int = 3
    retry_delay_s: float = 0.1

    def writable(self) -> bool:
        try:
            with self.path.open("a"):
                return True
        except OSError:
            return False

    def read(self) -> FanState:
        speed = 0
        level = "unknown"
        enabled = False
        for line in self.path.read_text().splitlines():
            if line.startswith("speed:"):
                try:
                    speed = int(line.split(":", 1)[1].strip())
                except ValueError:
                    speed = 0
            elif line.startswith("level:"):
                level = line.split(":", 1)[1].strip()
            elif line.startswith("status:"):
                enabled = line.split(":", 1)[1].strip() == "enabled"
        return FanState(speed_rpm=speed, level=level, enabled=enabled)

    def set_level(self, level: str) -> None:
        if level not in VALID_LEVELS:
            raise ValueError(f"invalid fan level: {level!r}")
        cmd = f"level {level}"
        writer = self._writer or self._default_writer
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                writer(cmd)
                return
            except OSError as e:
                last = e
                log.warning("fan write attempt %d failed: %s", attempt + 1, e)
                self._sleep(self.retry_delay_s)
        assert last is not None
        raise last

    def _default_writer(self, cmd: str) -> None:
        with self.path.open("w") as f:
            f.write(cmd)
```

- [ ] **Step 4: Tests laufen lassen — erwartet PASS**

Run: `.venv/bin/python -m pytest daemon/tests/test_fan.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add daemon/src/tpfan_daemon/hw/fan.py daemon/tests/test_fan.py
git commit -m "feat(daemon): /proc/acpi/ibm/fan wrapper with retries"
```

---

## Phase 2 — Daemon: Konfiguration

### Task 2.1: `config.py` — TOML-Load/Validate/Atomic-Write

**Files:**
- Create: `daemon/src/tpfan_daemon/config.py`
- Create: `daemon/tests/test_config.py`

- [ ] **Step 1: Test schreiben**

```python
# daemon/tests/test_config.py
from __future__ import annotations
from pathlib import Path
import pytest
from tpfan_daemon.config import Config, CurveCfg, load, save, DEFAULT


def test_load_default_when_missing(tmp_path: Path):
    cfg = load(tmp_path / "nope.toml")
    assert cfg == DEFAULT


def test_round_trip(tmp_path: Path):
    p = tmp_path / "c.toml"
    save(p, DEFAULT)
    cfg2 = load(p)
    assert cfg2 == DEFAULT


def test_validates_curve_monotonic(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text(
        '''
        mode = "curve"
        manual_level = "3"
        failsafe_temp = 95.0
        [curve]
        sensors = ["CPU"]
        points = [[70, 4], [55, 2]]
        '''
    )
    with pytest.raises(ValueError, match="monotonic"):
        load(p)


def test_validates_level_range(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text(
        '''
        mode = "curve"
        manual_level = "3"
        failsafe_temp = 95.0
        [curve]
        sensors = ["CPU"]
        points = [[40, 0], [80, 9]]
        '''
    )
    with pytest.raises(ValueError, match="level"):
        load(p)


def test_atomic_write_does_not_leave_partial(tmp_path: Path, monkeypatch):
    p = tmp_path / "c.toml"
    save(p, DEFAULT)
    original = p.read_text()

    def boom(*a, **kw):
        raise RuntimeError("disk full")

    monkeypatch.setattr("os.replace", boom)
    with pytest.raises(RuntimeError):
        save(p, CurveCfg.from_default()._wrap_in_config(failsafe_temp=70.0))
    assert p.read_text() == original
```

- [ ] **Step 2: Test laufen lassen — erwartet FAIL**

Run: `.venv/bin/python -m pytest daemon/tests/test_config.py -q`
Expected: FAIL

- [ ] **Step 3: `config.py` implementieren**

```python
# daemon/src/tpfan_daemon/config.py
from __future__ import annotations
from dataclasses import dataclass, field, replace
from pathlib import Path
import os
import tomllib
import logging

log = logging.getLogger(__name__)

VALID_LEVELS = {"0", "1", "2", "3", "4", "5", "6", "7", "auto", "disengaged"}


@dataclass(frozen=True)
class CurveCfg:
    sensors: tuple[str, ...]
    points: tuple[tuple[float, int], ...]

    @staticmethod
    def from_default() -> "CurveCfg":
        return CurveCfg(
            sensors=("CPU", "GPU", "NVMe"),
            points=((40.0, 0), (55.0, 2), (70.0, 4), (80.0, 7)),
        )

    def _wrap_in_config(self, **overrides) -> "Config":
        return replace(DEFAULT, curve=self, **overrides)


@dataclass(frozen=True)
class Config:
    mode: str = "curve"
    manual_level: str = "3"
    failsafe_temp: float = 95.0
    curve: CurveCfg = field(default_factory=CurveCfg.from_default)
    profiles: dict[str, CurveCfg] = field(default_factory=dict)


DEFAULT = Config(
    profiles={
        "quiet":       CurveCfg(("CPU", "GPU", "NVMe"), ((50.0, 0), (65.0, 1), (75.0, 3), (85.0, 7))),
        "balanced":    CurveCfg(("CPU", "GPU", "NVMe"), ((40.0, 0), (55.0, 2), (70.0, 4), (80.0, 7))),
        "performance": CurveCfg(("CPU", "GPU", "NVMe"), ((35.0, 1), (50.0, 3), (65.0, 5), (75.0, 7))),
    }
)


def _validate_points(points: list[list[float]]) -> tuple[tuple[float, int], ...]:
    if len(points) < 2:
        raise ValueError("curve must have at least 2 points")
    out: list[tuple[float, int]] = []
    prev_t: float | None = None
    for pt in points:
        if len(pt) != 2:
            raise ValueError(f"bad point: {pt}")
        t, lvl = float(pt[0]), int(pt[1])
        if not (20.0 <= t <= 110.0):
            raise ValueError(f"temperature out of range: {t}")
        if not (0 <= lvl <= 7):
            raise ValueError(f"level out of range: {lvl}")
        if prev_t is not None and t <= prev_t:
            raise ValueError("temperatures must be strictly monotonic")
        prev_t = t
        out.append((t, lvl))
    return tuple(out)


def _validate_curve(d: dict) -> CurveCfg:
    sensors = tuple(d.get("sensors", ("CPU",)))
    points = _validate_points(d.get("points", []))
    return CurveCfg(sensors=sensors, points=points)


def load(path: Path) -> Config:
    if not path.exists():
        return DEFAULT
    with path.open("rb") as f:
        raw = tomllib.load(f)
    mode = raw.get("mode", DEFAULT.mode)
    manual_level = str(raw.get("manual_level", DEFAULT.manual_level))
    if manual_level not in VALID_LEVELS:
        raise ValueError(f"invalid manual_level: {manual_level}")
    failsafe_temp = float(raw.get("failsafe_temp", DEFAULT.failsafe_temp))
    curve = _validate_curve(raw["curve"]) if "curve" in raw else DEFAULT.curve
    profiles = {k: _validate_curve(v) for k, v in raw.get("profiles", {}).items()}
    return Config(mode=mode, manual_level=manual_level,
                  failsafe_temp=failsafe_temp, curve=curve, profiles=profiles)


def _serialize(cfg: Config) -> str:
    def _curve(c: CurveCfg) -> str:
        s = "sensors = [" + ", ".join(f'"{x}"' for x in c.sensors) + "]\n"
        pts = ", ".join(f"[{t}, {l}]" for t, l in c.points)
        s += f"points = [{pts}]\n"
        return s

    out = []
    out.append(f'mode = "{cfg.mode}"')
    out.append(f'manual_level = "{cfg.manual_level}"')
    out.append(f"failsafe_temp = {cfg.failsafe_temp}")
    out.append("")
    out.append("[curve]")
    out.append(_curve(cfg.curve))
    for name, c in cfg.profiles.items():
        out.append(f"[profiles.{name}]")
        out.append(_curve(c))
    return "\n".join(out)


def save(path: Path, cfg: Config) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(_serialize(cfg))
    os.replace(tmp, path)
```

- [ ] **Step 4: Tests laufen lassen — erwartet PASS**

Run: `.venv/bin/python -m pytest daemon/tests/test_config.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add daemon/src/tpfan_daemon/config.py daemon/tests/test_config.py
git commit -m "feat(daemon): TOML config with validation and atomic write"
```

---

## Phase 3 — Daemon: Curve-Engine

### Task 3.1: `control/curve.py` — Interpolation und Hysterese

**Files:**
- Create: `daemon/src/tpfan_daemon/control/__init__.py`
- Create: `daemon/src/tpfan_daemon/control/curve.py`
- Create: `daemon/tests/test_curve.py`

Semantik:
- Eingabe ist Temperatur T und vorheriges Level `prev`.
- Punkte definieren stückweise lineare Kurve in Level-Domäne; Ausgabe wird auf `int` gerundet, geclampt auf 0..7.
- Hysterese: ein Level fällt erst zurück, wenn T um ≥ 3 °C unter den Schwellpunkt fällt, an dem das aktuelle Level erstmals erreicht wurde.

- [ ] **Step 1: Test schreiben**

```python
# daemon/tests/test_curve.py
from __future__ import annotations
import pytest
from tpfan_daemon.control.curve import interpolate, threshold_for_level

POINTS = [(40.0, 0), (55.0, 2), (70.0, 4), (80.0, 7)]


@pytest.mark.parametrize("t,prev,expected", [
    (30.0, 0, 0),
    (40.0, 0, 0),
    (47.5, 0, 1),
    (55.0, 0, 2),
    (62.5, 0, 3),
    (70.0, 0, 4),
    (75.0, 0, 6),
    (80.0, 0, 7),
    (95.0, 0, 7),
])
def test_steigend_keine_hysterese(t, prev, expected):
    assert interpolate(POINTS, t, prev) == expected


def test_hysterese_haelt_level_bei_kleinem_drop():
    assert interpolate(POINTS, 68.0, 4) == 4


def test_hysterese_release_unter_drei_grad():
    assert interpolate(POINTS, 60.0, 4) == 3


def test_threshold_for_level():
    assert threshold_for_level(POINTS, 4) == 70.0
    assert threshold_for_level(POINTS, 2) == 55.0
    assert threshold_for_level(POINTS, 1) == pytest.approx(47.5)


def test_unter_erstem_punkt_clampt():
    assert interpolate(POINTS, 10.0, 0) == 0


def test_zwei_punkte_minimal():
    assert interpolate([(40.0, 0), (80.0, 7)], 60.0, 0) == 4
```

- [ ] **Step 2: Test laufen lassen — erwartet FAIL**

Run: `.venv/bin/python -m pytest daemon/tests/test_curve.py -q`
Expected: FAIL

- [ ] **Step 3: `curve.py` implementieren**

```python
# daemon/src/tpfan_daemon/control/__init__.py
```

```python
# daemon/src/tpfan_daemon/control/curve.py
from __future__ import annotations
from typing import Sequence

HYSTERESIS_C = 3.0
Point = tuple[float, int]


def _raw_level(points: Sequence[Point], t: float) -> float:
    if t <= points[0][0]:
        return float(points[0][1])
    if t >= points[-1][0]:
        return float(points[-1][1])
    for (t0, l0), (t1, l1) in zip(points, points[1:]):
        if t0 <= t <= t1:
            f = (t - t0) / (t1 - t0)
            return l0 + f * (l1 - l0)
    return float(points[-1][1])


def threshold_for_level(points: Sequence[Point], level: int) -> float:
    if level <= points[0][1]:
        return points[0][0]
    if level >= points[-1][1]:
        return points[-1][0]
    for (t0, l0), (t1, l1) in zip(points, points[1:]):
        if l0 <= level <= l1 and l1 > l0:
            f = (level - l0) / (l1 - l0)
            return t0 + f * (t1 - t0)
    return points[-1][0]


def interpolate(points: Sequence[Point], t: float, prev_level: int) -> int:
    raw = round(_raw_level(points, t))
    raw = max(0, min(7, raw))
    if raw >= prev_level:
        return raw
    thr = threshold_for_level(points, prev_level)
    if t >= thr - HYSTERESIS_C:
        return prev_level
    return raw
```

- [ ] **Step 4: Tests laufen lassen — erwartet PASS**

Run: `.venv/bin/python -m pytest daemon/tests/test_curve.py -q`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add daemon/src/tpfan_daemon/control daemon/tests/test_curve.py
git commit -m "feat(daemon): fan curve engine with hysteresis"
```

---

## Phase 4 — Daemon: Control-Loop

### Task 4.1: `control/loop.py` — 1 Hz-Regelschleife mit Modi und Failsafe

**Files:**
- Create: `daemon/src/tpfan_daemon/control/loop.py`
- Create: `daemon/tests/test_loop.py`

Verantwortung: pro Tick `read_all_sensors`, `read_fan`, dann Modus-Auswertung → Ziel-Level → ggf. `set_level`. Failsafe vor allem. Liefert pro Tick ein `TickResult` für D-Bus-Push.

- [ ] **Step 1: Test schreiben**

```python
# daemon/tests/test_loop.py
from __future__ import annotations
from dataclasses import dataclass
from tpfan_daemon.control.loop import ControlLoop
from tpfan_daemon.config import Config, CurveCfg, DEFAULT


class FakeSensors:
    def __init__(self, temps): self.temps = temps
    def read_all(self): return dict(self.temps)


class FakeFan:
    def __init__(self):
        self.level = "auto"
        self.history: list[str] = []
        self.fail_set: bool = False

    def read(self):
        @dataclass
        class S:
            speed_rpm: int = 2000
            level: str = "auto"
            enabled: bool = True
        s = S()
        s.level = self.level
        return s

    def set_level(self, lvl):
        if self.fail_set:
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
```

- [ ] **Step 2: Test laufen lassen — erwartet FAIL**

Run: `.venv/bin/python -m pytest daemon/tests/test_loop.py -q`
Expected: FAIL

- [ ] **Step 3: `loop.py` implementieren**

```python
# daemon/src/tpfan_daemon/control/loop.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
import logging

from .curve import interpolate
from ..config import Config, CurveCfg

log = logging.getLogger(__name__)


class SensorsLike(Protocol):
    def read_all(self) -> dict[str, float]: ...


class FanLike(Protocol):
    def read(self): ...
    def set_level(self, level: str) -> None: ...


@dataclass
class TickResult:
    temps: dict[str, float]
    fan_speed: int
    current_level: str
    target_level: str
    emergency: tuple[float, str] | None = None
    fallback_to_auto: bool = False


@dataclass
class ControlLoop:
    sensors: SensorsLike
    fan: FanLike
    config: Config
    _last_level: str = "auto"
    _last_curve_level: int = 0

    def set_config(self, cfg: Config) -> None:
        self.config = cfg

    def _active_curve(self) -> CurveCfg | None:
        m = self.config.mode
        if m == "curve":
            return self.config.curve
        if m.startswith("profile:"):
            name = m.split(":", 1)[1]
            return self.config.profiles.get(name)
        return None

    def tick(self) -> TickResult:
        temps = self.sensors.read_all()
        st = self.fan.read()
        current = st.level

        target: str
        emergency: tuple[float, str] | None = None
        fallback = False

        if temps:
            hot = max(temps.items(), key=lambda kv: kv[1])
            if hot[1] >= self.config.failsafe_temp:
                target = "disengaged"
                emergency = (hot[1], hot[0])
                try:
                    self.fan.set_level(target)
                except OSError as e:
                    log.error("emergency fan write failed: %s", e)
                self._last_level = target
                return TickResult(temps, st.speed_rpm, current, target, emergency)
        else:
            target = "auto"
            try:
                if current != target:
                    self.fan.set_level(target)
                self._last_level = target
            except OSError:
                fallback = True
            return TickResult(temps, st.speed_rpm, current, target,
                              fallback_to_auto=fallback)

        m = self.config.mode
        if m == "auto":
            target = "auto"
        elif m == "manual":
            target = self.config.manual_level
        else:
            curve = self._active_curve()
            if curve is None:
                target = "auto"
            else:
                values = [temps[s] for s in curve.sensors if s in temps]
                if not values:
                    target = "auto"
                else:
                    t = max(values)
                    prev = self._last_curve_level
                    lvl = interpolate(curve.points, t, prev)
                    self._last_curve_level = lvl
                    target = str(lvl)

        try:
            if target != current:
                self.fan.set_level(target)
            self._last_level = target
        except OSError as e:
            log.error("fan write failed permanently: %s — falling back to auto", e)
            try:
                self.fan.set_level("auto")
                self._last_level = "auto"
            except OSError:
                pass
            fallback = True

        return TickResult(temps, st.speed_rpm, current, target,
                          emergency=emergency, fallback_to_auto=fallback)
```

- [ ] **Step 4: Tests laufen lassen — erwartet PASS**

Run: `.venv/bin/python -m pytest daemon/tests/test_loop.py -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add daemon/src/tpfan_daemon/control/loop.py daemon/tests/test_loop.py
git commit -m "feat(daemon): 1 Hz control loop with failsafe and mode logic"
```

---

## Phase 5 — Daemon: D-Bus-Service

### Task 5.1: `ipc/dbus_service.py` — Skeleton mit `dasbus`

**Files:**
- Create: `daemon/src/tpfan_daemon/ipc/__init__.py`
- Create: `daemon/src/tpfan_daemon/ipc/dbus_service.py`
- Create: `daemon/tests/test_dbus.py`

Service-Interface basiert auf `dasbus`. Properties werden bei Loop-Tick aktualisiert; `PropertiesChanged`-Signale werden vom Framework geworfen.

- [ ] **Step 1: Test schreiben (Session-Bus)**

```python
# daemon/tests/test_dbus.py
from __future__ import annotations
import os, shutil, signal, subprocess, time, pytest
from pathlib import Path


@pytest.fixture
def session_bus(tmp_path: Path):
    if shutil.which("dbus-daemon") is None:
        pytest.skip("dbus-daemon not available")
    conf = tmp_path / "session.conf"
    conf.write_text(f"""<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <type>session</type>
  <listen>unix:tmpdir={tmp_path}</listen>
  <policy context="default"><allow send_destination="*"/><allow own="*"/><allow receive_sender="*"/></policy>
</busconfig>
""")
    addr_file = tmp_path / "addr"
    proc = subprocess.Popen([
        "dbus-daemon", f"--config-file={conf}",
        "--print-address=1", "--nofork",
    ], stdout=open(addr_file, "wb"))
    time.sleep(0.4)
    addr = addr_file.read_text().strip()
    if not addr:
        proc.kill(); pytest.skip("could not read session bus address")
    os.environ["DBUS_SESSION_BUS_ADDRESS"] = addr
    yield addr
    proc.send_signal(signal.SIGTERM); proc.wait(timeout=5)


def test_service_exposes_properties_and_methods(session_bus):
    from dasbus.connection import SessionMessageBus
    from tpfan_daemon.ipc.dbus_service import TpfanService, BUS_NAME, OBJECT_PATH
    from tpfan_daemon.config import DEFAULT

    state = {
        "mode": "auto",
        "level": "auto",
        "temps": {"CPU": 42.0, "GPU": 45.0},
        "sensor_describe": {"CPU": (42.0, "CPU", "k10temp/Tctl")},
        "fans": [(2200, "auto"), (2100, "auto")],
        "curve": DEFAULT.curve,
        "curve_sensors": list(DEFAULT.curve.sensors),
        "failsafe_temp": DEFAULT.failsafe_temp,
    }
    svc = TpfanService(state_getter=lambda: state, command_handler=lambda *a, **k: None)
    bus = SessionMessageBus()
    bus.publish_object(OBJECT_PATH, svc)
    bus.register_service(BUS_NAME)

    proxy = bus.get_proxy(BUS_NAME, OBJECT_PATH)
    assert proxy.Mode == "auto"
    assert proxy.CurrentLevel == "auto"
    assert "CPU" in proxy.Sensors
    assert proxy.DaemonVersion
```

- [ ] **Step 2: Test laufen lassen — erwartet FAIL**

Run: `.venv/bin/python -m pytest daemon/tests/test_dbus.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: `dbus_service.py` implementieren**

```python
# daemon/src/tpfan_daemon/ipc/__init__.py
```

```python
# daemon/src/tpfan_daemon/ipc/dbus_service.py
from __future__ import annotations
from typing import Callable
from dasbus.server.interface import dbus_interface, dbus_signal
from dasbus.typing import Str, Double, UInt32, List, Tuple, Dict, Byte
from .. import __version__

BUS_NAME = "org.tpfan1"
OBJECT_PATH = "/org/tpfan1"
IFACE = "org.tpfan1"


@dbus_interface(IFACE)
class TpfanService:
    """state_getter() liefert ein Dict mit Live-Daten;
    command_handler(name, *args) behandelt schreibende Calls."""

    def __init__(self, state_getter: Callable[[], dict], command_handler: Callable,
                 authorizer: Callable | None = None,
                 sender_getter: Callable[[], str] | None = None):
        self._state = state_getter
        self._cmd = command_handler
        self._authz = authorizer
        self._sender = sender_getter

    def _check(self, action: str) -> None:
        if self._authz is None:
            return
        sender = self._sender() if self._sender else ""
        self._authz(sender, action)

    # --- Properties ---
    @property
    def Sensors(self) -> Dict[Str, Tuple[Double, Str, Str]]:
        out = {}
        for name, (val, label, source) in self._state().get("sensor_describe", {}).items():
            out[name] = (val, label, source)
        if not out:
            for name, val in self._state().get("temps", {}).items():
                out[name] = (val, name, name)
        return out

    @property
    def Fans(self) -> List[Tuple[UInt32, UInt32]]:
        fans = self._state().get("fans", [])
        out: list[tuple[int, int]] = []
        for rpm, lvl in fans:
            try:
                lvl_n = int(lvl) if str(lvl).isdigit() else 0xFF
            except (ValueError, TypeError):
                lvl_n = 0xFF
            out.append((int(rpm), lvl_n))
        return out

    @property
    def Mode(self) -> Str:
        return self._state().get("mode", "auto")

    @property
    def CurrentLevel(self) -> Str:
        return self._state().get("level", "auto")

    @property
    def Curve(self) -> List[Tuple[Double, Byte]]:
        return [(float(t), int(l)) for t, l in self._state().get("curve").points]

    @property
    def CurveSensors(self) -> List[Str]:
        return list(self._state().get("curve_sensors", []))

    @property
    def FailsafeTemp(self) -> Double:
        return float(self._state().get("failsafe_temp", 95.0))

    @property
    def DaemonVersion(self) -> Str:
        return __version__

    # --- Methoden ---
    def SetMode(self, mode: Str) -> None:
        self._check("org.tpfan1.set-mode")
        self._cmd("set_mode", mode)

    def SetCurve(self, points: List[Tuple[Double, Byte]], sensors: List[Str]) -> None:
        self._check("org.tpfan1.set-curve")
        self._cmd("set_curve", [(float(t), int(l)) for t, l in points], list(sensors))

    def SetManualLevel(self, level: Str) -> None:
        self._check("org.tpfan1.set-manual-level")
        self._cmd("set_manual_level", level)

    def SetFailsafeTemp(self, temp: Double) -> None:
        self._check("org.tpfan1.set-failsafe-temp")
        self._cmd("set_failsafe_temp", float(temp))

    def ReloadConfig(self) -> None:
        self._check("org.tpfan1.reload-config")
        self._cmd("reload_config")

    # --- Signale ---
    @dbus_signal
    def Tick(self, temps: Dict[Str, Double], fans: List[Tuple[UInt32, UInt32]], level: Str):
        pass

    @dbus_signal
    def EmergencyTriggered(self, temp: Double, sensor: Str):
        pass
```

- [ ] **Step 4: Test laufen lassen — erwartet PASS (oder skip wenn dbus-daemon fehlt)**

Run: `.venv/bin/python -m pytest daemon/tests/test_dbus.py -q`
Expected: 1 passed oder skipped

- [ ] **Step 5: Commit**

```bash
git add daemon/src/tpfan_daemon/ipc daemon/tests/test_dbus.py
git commit -m "feat(daemon): D-Bus service interface (org.tpfan1)"
```

### Task 5.2: PolicyKit-Helfer

**Files:**
- Create: `daemon/src/tpfan_daemon/ipc/polkit.py`
- Create: `daemon/tests/test_polkit.py`

- [ ] **Step 1: Test schreiben**

```python
# daemon/tests/test_polkit.py
from __future__ import annotations
from tpfan_daemon.ipc.polkit import authorize, PolkitError
import pytest


class FakeBus:
    def __init__(self, allowed: bool):
        self.allowed = allowed
        self.calls: list = []

    def get_proxy(self, *a, **kw):
        bus = self

        class P:
            def CheckAuthorization(self, subject, action_id, details, flags, cancel_id):
                bus.calls.append((action_id,))
                return (bus.allowed, False, {})
        return P()


def test_authorize_allowed():
    bus = FakeBus(True)
    authorize(bus, sender=":1.42", action="org.tpfan1.set-mode")
    assert bus.calls[0][0] == "org.tpfan1.set-mode"


def test_authorize_denied_raises():
    bus = FakeBus(False)
    with pytest.raises(PolkitError):
        authorize(bus, sender=":1.42", action="org.tpfan1.set-mode")
```

- [ ] **Step 2: Test laufen lassen — erwartet FAIL**

Run: `.venv/bin/python -m pytest daemon/tests/test_polkit.py -q`
Expected: FAIL

- [ ] **Step 3: `polkit.py` implementieren**

```python
# daemon/src/tpfan_daemon/ipc/polkit.py
from __future__ import annotations


class PolkitError(Exception):
    pass


def authorize(bus, sender: str, action: str) -> None:
    """Synchroner PolicyKit-CheckAuthorization."""
    proxy = bus.get_proxy(
        "org.freedesktop.PolicyKit1",
        "/org/freedesktop/PolicyKit1/Authority",
        "org.freedesktop.PolicyKit1.Authority",
    )
    subject = (
        "system-bus-name",
        {"name": ("s", sender)},
    )
    is_auth, _challenge, _details = proxy.CheckAuthorization(
        subject, action, {}, 1, ""
    )
    if not is_auth:
        raise PolkitError(f"polkit denied: {action}")
```

- [ ] **Step 4: Tests laufen lassen — erwartet PASS**

Run: `.venv/bin/python -m pytest daemon/tests/test_polkit.py -q`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add daemon/src/tpfan_daemon/ipc/polkit.py daemon/tests/test_polkit.py
git commit -m "feat(daemon): polkit authorization helper"
```

---

## Phase 6 — Daemon: Command-Handler und Main

### Task 6.1: `daemon.py` — Glue: Loop + Config-Persistierung + Validierung

**Files:**
- Create: `daemon/src/tpfan_daemon/daemon.py`
- Create: `daemon/tests/test_daemon_glue.py`

- [ ] **Step 1: Test schreiben**

```python
# daemon/tests/test_daemon_glue.py
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
```

- [ ] **Step 2: Test laufen lassen — erwartet FAIL**

Run: `.venv/bin/python -m pytest daemon/tests/test_daemon_glue.py -q`
Expected: FAIL

- [ ] **Step 3: `daemon.py` implementieren**

```python
# daemon/src/tpfan_daemon/daemon.py
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
from typing import Any
import logging

from .config import CurveCfg, DEFAULT, load, save, _validate_points, VALID_LEVELS
from .control.loop import ControlLoop

log = logging.getLogger(__name__)


class Daemon:
    def __init__(self, config_path: Path, sensors, fan):
        self.config_path = config_path
        self.sensors = sensors
        self.fan = fan
        cfg = load(config_path) if config_path.exists() else DEFAULT
        if not config_path.exists():
            save(config_path, cfg)
        self.loop = ControlLoop(sensors=sensors, fan=fan, config=cfg)

    def _save(self) -> None:
        save(self.config_path, self.loop.config)

    def handle(self, cmd: str, *args: Any) -> None:
        if cmd == "set_mode":
            mode = args[0]
            if not (mode in ("auto", "curve", "manual") or mode.startswith("profile:")):
                raise ValueError(f"unknown mode: {mode}")
            if mode.startswith("profile:") and mode.split(":", 1)[1] not in self.loop.config.profiles:
                raise ValueError(f"unknown profile: {mode}")
            self.loop.set_config(replace(self.loop.config, mode=mode))
            self._save()
        elif cmd == "set_curve":
            points, sensors_ = args
            pts = _validate_points([list(p) for p in points])
            known = set(self.sensors.read_all().keys())
            for s in sensors_:
                if s not in known:
                    raise ValueError(f"unknown sensor: {s}")
            curve = CurveCfg(sensors=tuple(sensors_), points=pts)
            self.loop.set_config(replace(self.loop.config, curve=curve))
            self._save()
        elif cmd == "set_manual_level":
            lvl = args[0]
            if self.loop.config.mode != "manual":
                raise ValueError("SetManualLevel requires mode=manual")
            if lvl not in VALID_LEVELS:
                raise ValueError(f"invalid level: {lvl}")
            self.loop.set_config(replace(self.loop.config, manual_level=lvl))
            self._save()
        elif cmd == "set_failsafe_temp":
            t = float(args[0])
            if not (40.0 <= t <= 110.0):
                raise ValueError("failsafe out of range")
            self.loop.set_config(replace(self.loop.config, failsafe_temp=t))
            self._save()
        elif cmd == "reload_config":
            self.loop.set_config(load(self.config_path))
        else:
            raise ValueError(f"unknown command: {cmd}")
```

- [ ] **Step 4: Tests laufen lassen — erwartet PASS**

Run: `.venv/bin/python -m pytest daemon/tests/test_daemon_glue.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add daemon/src/tpfan_daemon/daemon.py daemon/tests/test_daemon_glue.py
git commit -m "feat(daemon): command handler wiring loop, config and validation"
```

### Task 6.2: `__main__.py` — Bootstrap, systemd-Watchdog, Signal-Handling

**Files:**
- Create: `daemon/src/tpfan_daemon/__main__.py`

Hinweis: kein automatischer Test, da System-Bus-Registrierung und systemd benötigt werden. Smoke-Test in der manuellen Checkliste (Phase 12).

- [ ] **Step 1: `__main__.py` schreiben**

```python
# daemon/src/tpfan_daemon/__main__.py
from __future__ import annotations
import logging, os, signal, sys
from pathlib import Path

from gi.repository import GLib
from dasbus.connection import SystemMessageBus

from .daemon import Daemon
from .hw.sensors import Sensors
from .hw.fan import Fan
from .ipc.dbus_service import TpfanService, BUS_NAME, OBJECT_PATH
from .ipc.polkit import authorize

CONFIG_PATH = Path(os.environ.get("TPFAN_CONFIG", "/etc/tpfan/config.toml"))


def _setup_logging():
    level = os.environ.get("TPFAN_LOG", "info").upper()
    logging.basicConfig(level=getattr(logging, level, logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        stream=sys.stderr)


def _sd_notify(msg: str) -> None:
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return
    import socket
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        if addr.startswith("@"):
            addr = "\0" + addr[1:]
        s.sendto(msg.encode(), addr)
    finally:
        s.close()


def main() -> int:
    _setup_logging()
    log = logging.getLogger("tpfan-daemon")

    sensors = Sensors()
    sensors.discover()
    fan = Fan()
    if not fan.writable():
        log.error("/proc/acpi/ibm/fan not writable — load thinkpad_acpi with fan_control=1")
        return 1

    daemon = Daemon(CONFIG_PATH, sensors, fan)
    bus = SystemMessageBus()

    def authorizer(sender: str, action: str) -> None:
        authorize(bus, sender, action)

    service = TpfanService(
        state_getter=lambda: _state_dict(daemon, sensors),
        command_handler=daemon.handle,
        authorizer=authorizer,
        sender_getter=lambda: "",
    )

    bus.publish_object(OBJECT_PATH, service)
    bus.register_service(BUS_NAME)

    _sd_notify("READY=1")
    main_loop = GLib.MainLoop()

    def shutdown(*_):
        log.info("shutdown — resetting fan to auto")
        try: fan.set_level("auto")
        except Exception: pass
        main_loop.quit()

    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, shutdown)

    def tick():
        try:
            tr = daemon.loop.tick()
            fan_state = fan.read()
            fans_payload = [(fan_state.speed_rpm, _lvl_to_int(tr.target_level))]
            service.Tick(tr.temps, fans_payload, tr.target_level)
            if tr.emergency:
                service.EmergencyTriggered(tr.emergency[0], tr.emergency[1])
            _sd_notify("WATCHDOG=1")
        except Exception:
            log.exception("tick failed")
        return True

    GLib.timeout_add_seconds(1, tick)
    main_loop.run()
    return 0


def _state_dict(d: Daemon, sensors: Sensors) -> dict:
    return {
        "mode": d.loop.config.mode,
        "level": d.loop._last_level,
        "temps": sensors.read_all(),
        "sensor_describe": sensors.describe(),
        "fans": [],
        "curve": d.loop.config.curve,
        "curve_sensors": list(d.loop.config.curve.sensors),
        "failsafe_temp": d.loop.config.failsafe_temp,
    }


def _lvl_to_int(lvl: str) -> int:
    return int(lvl) if lvl.isdigit() else 0xFF


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Manueller Syntax-Check**

Run: `.venv/bin/python -c "import tpfan_daemon.__main__"`
Expected: kein Output. Bei ImportError für `gi`: `sudo dnf install python3-gobject` empfehlen — gehört zur System-Integration.

- [ ] **Step 3: Commit**

```bash
git add daemon/src/tpfan_daemon/__main__.py
git commit -m "feat(daemon): main entrypoint with systemd watchdog and D-Bus loop"
```

---

## Phase 7 — Daemon: Integrationstest und Coverage

### Task 7.1: End-to-End Loop mit Fake-HW

**Files:**
- Create: `daemon/tests/test_integration.py`

- [ ] **Step 1: Test schreiben**

```python
# daemon/tests/test_integration.py
from __future__ import annotations
from pathlib import Path
from tpfan_daemon.daemon import Daemon


class DriveSensors:
    def __init__(self, schedule):
        self.schedule = schedule
        self.i = 0
    def read_all(self):
        r = self.schedule[min(self.i, len(self.schedule) - 1)]
        self.i += 1
        return dict(r)
    def describe(self):
        return {}


class RememberFan:
    def __init__(self): self.level = "auto"; self.history = []
    def writable(self): return True
    def read(self):
        class S: pass
        s = S(); s.level = self.level; s.speed_rpm = 2000; s.enabled = True
        return s
    def set_level(self, lvl):
        self.level = lvl
        self.history.append(lvl)


def test_curve_drives_fan_over_temp_sweep(tmp_path: Path):
    cfg_path = tmp_path / "c.toml"
    fan = RememberFan()
    schedule = [
        {"CPU": 40.0},   # -> 0
        {"CPU": 55.0},   # -> 2
        {"CPU": 70.0},   # -> 4
        {"CPU": 80.0},   # -> 7
        {"CPU": 78.0},   # Hysterese: bleibt 7
        {"CPU": 60.0},   # deutlich unter Schwelle: drop
    ]
    d = Daemon(cfg_path, DriveSensors(schedule), fan)
    d.handle("set_mode", "curve")
    d.handle("set_curve", [(40.0, 0), (55.0, 2), (70.0, 4), (80.0, 7)], ["CPU"])

    for _ in range(len(schedule)):
        d.loop.tick()

    assert fan.history[:4] == ["0", "2", "4", "7"]
    assert fan.history[-1] in ("2", "3")
```

- [ ] **Step 2: Tests laufen lassen — erwartet PASS**

Run: `.venv/bin/python -m pytest daemon/tests/test_integration.py -q`
Expected: 1 passed

- [ ] **Step 3: Coverage prüfen für `hw/`, `control/`, `config.py`**

Run: `.venv/bin/python -m pytest daemon/tests --cov=tpfan_daemon.hw --cov=tpfan_daemon.control --cov=tpfan_daemon.config --cov-report=term-missing -q`
Expected: Coverage ≥ 90 % für genannte Module. Falls darunter: fehlende Zweige durch zusätzliche Tests adressieren.

- [ ] **Step 4: Commit**

```bash
git add daemon/tests/test_integration.py
git commit -m "test(daemon): integration sweep covering hysteresis transitions"
```

---

## Phase 8 — Packaging-Dateien (System-Integration)

### Task 8.1: systemd, D-Bus, polkit, modprobe, Desktop-Entry

**Files:**
- Create: `packaging/tpfan-daemon.service`
- Create: `packaging/tpfan-daemon-launcher`
- Create: `packaging/tpfan-gui-launcher`
- Create: `packaging/org.tpfan1.conf`
- Create: `packaging/org.tpfan1.service`
- Create: `packaging/org.tpfan1.policy`
- Create: `packaging/tpfan-modprobe.conf`
- Create: `packaging/tpfan-gui.desktop`

- [ ] **Step 1: systemd-Unit**

```ini
# packaging/tpfan-daemon.service
[Unit]
Description=tpfan — ThinkPad Fan Control Daemon
After=systemd-modules-load.service

[Service]
Type=dbus
BusName=org.tpfan1
ExecStart=/usr/local/bin/tpfan-daemon
WatchdogSec=10
Restart=on-failure
NotifyAccess=main
Environment=TPFAN_LOG=info

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Launcher-Scripts**

```bash
# packaging/tpfan-daemon-launcher
#!/usr/bin/env bash
exec /usr/bin/python3 -m tpfan_daemon "$@"
```

```bash
# packaging/tpfan-gui-launcher
#!/usr/bin/env bash
exec /usr/bin/python3 -m tpfan_gui "$@"
```

- [ ] **Step 3: D-Bus Bus-Policy (`org.tpfan1.conf`)**

```xml
<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <policy user="root">
    <allow own="org.tpfan1"/>
  </policy>
  <policy context="default">
    <allow send_destination="org.tpfan1"/>
    <allow receive_sender="org.tpfan1"/>
  </policy>
</busconfig>
```

- [ ] **Step 4: D-Bus System-Service**

```ini
# packaging/org.tpfan1.service
[D-BUS Service]
Name=org.tpfan1
Exec=/usr/local/bin/tpfan-daemon
User=root
SystemdService=tpfan-daemon.service
```

- [ ] **Step 5: PolicyKit-Action-Datei**

```xml
<!-- packaging/org.tpfan1.policy -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC
 "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/PolicyKit/1/policyconfig.dtd">
<policyconfig>
  <vendor>tpfan</vendor>

  <action id="org.tpfan1.set-mode">
    <description>Lüfter-Modus ändern</description>
    <message>Authentifizierung erforderlich, um den Lüfter-Modus zu ändern.</message>
    <defaults>
      <allow_active>auth_admin_keep</allow_active>
    </defaults>
  </action>

  <action id="org.tpfan1.set-curve">
    <description>Lüfter-Kurve ändern</description>
    <message>Authentifizierung erforderlich, um die Lüfter-Kurve zu ändern.</message>
    <defaults><allow_active>auth_admin_keep</allow_active></defaults>
  </action>

  <action id="org.tpfan1.set-manual-level">
    <description>Manuelles Lüfter-Level setzen</description>
    <defaults><allow_active>auth_admin_keep</allow_active></defaults>
  </action>

  <action id="org.tpfan1.set-failsafe-temp">
    <description>Failsafe-Temperatur ändern</description>
    <defaults><allow_active>auth_admin_keep</allow_active></defaults>
  </action>

  <action id="org.tpfan1.reload-config">
    <description>Konfiguration neu laden</description>
    <defaults><allow_active>auth_admin_keep</allow_active></defaults>
  </action>
</policyconfig>
```

- [ ] **Step 6: modprobe-Konfig**

```
# packaging/tpfan-modprobe.conf
options thinkpad_acpi fan_control=1
```

- [ ] **Step 7: Desktop-Entry**

```ini
# packaging/tpfan-gui.desktop
[Desktop Entry]
Type=Application
Name=tpfan
Comment=ThinkPad Lüfter-Steuerung
Exec=tpfan-gui
Icon=fan
Categories=System;Settings;
Terminal=false
```

- [ ] **Step 8: Permissions setzen und Commit**

```bash
chmod +x packaging/tpfan-daemon-launcher packaging/tpfan-gui-launcher
git add packaging/
git commit -m "feat: systemd, D-Bus, polkit, modprobe and desktop packaging"
```

---

## Phase 9 — GUI: D-Bus-Client

### Task 9.1: `ipc/dbus_client.py` — D-Bus → Qt-Signals

**Files:**
- Create: `gui/src/tpfan_gui/ipc/__init__.py`
- Create: `gui/src/tpfan_gui/ipc/dbus_client.py`
- Create: `gui/tests/test_dbus_client.py`

- [ ] **Step 1: Test schreiben (reine Übersetzungslogik, kein D-Bus)**

```python
# gui/tests/test_dbus_client.py
from __future__ import annotations


def test_translate_tick_signal_to_payload():
    from tpfan_gui.ipc.dbus_client import translate_tick

    payload = translate_tick(
        {"CPU": 50.0, "GPU": 55.0},
        [(2200, 0xFF), (2100, 0xFF)],
        "auto",
    )
    assert payload.temps == {"CPU": 50.0, "GPU": 55.0}
    assert payload.fans == [(2200, "auto"), (2100, "auto")]
    assert payload.level == "auto"


def test_translate_numeric_level():
    from tpfan_gui.ipc.dbus_client import translate_tick
    payload = translate_tick({"CPU": 50.0}, [(3000, 5)], "5")
    assert payload.fans[0] == (3000, "5")
    assert payload.level == "5"
```

- [ ] **Step 2: Test laufen lassen — erwartet FAIL**

Run: `.venv/bin/python -m pytest gui/tests/test_dbus_client.py -q`
Expected: FAIL

- [ ] **Step 3: `dbus_client.py` implementieren**

```python
# gui/src/tpfan_gui/ipc/__init__.py
```

```python
# gui/src/tpfan_gui/ipc/dbus_client.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import logging

log = logging.getLogger(__name__)

BUS_NAME = "org.tpfan1"
OBJECT_PATH = "/org/tpfan1"


@dataclass(frozen=True)
class TickPayload:
    temps: dict[str, float]
    fans: list[tuple[int, str]]
    level: str


def _level_int_to_str(n: int) -> str:
    if n == 0xFF:
        return "auto"
    if 0 <= n <= 7:
        return str(n)
    return "unknown"


def translate_tick(temps: dict[str, float],
                   fans_raw: list[tuple[int, int]],
                   level: str) -> TickPayload:
    return TickPayload(
        temps=dict(temps),
        fans=[(int(rpm), _level_int_to_str(int(lvl))) for rpm, lvl in fans_raw],
        level=str(level),
    )


def make_client(parent=None):
    """Lazy-Erstellung des Qt+D-Bus-Clients (PyQt6 nur hier importieren,
    damit Logik-Tests headless laufen)."""
    from PyQt6.QtCore import QObject, pyqtSignal, QTimer
    from dasbus.connection import SystemMessageBus
    from dasbus.error import DBusError

    class Client(QObject):
        tickReceived = pyqtSignal(object)
        propertiesChanged = pyqtSignal(dict)
        emergency = pyqtSignal(float, str)
        connected = pyqtSignal(bool)

        def __init__(self, parent=None):
            super().__init__(parent)
            self._bus: Optional[SystemMessageBus] = None
            self._proxy = None
            self._reconnect = QTimer(self)
            self._reconnect.setInterval(2000)
            self._reconnect.timeout.connect(self._try_connect)
            self._reconnect.start()
            self._try_connect()

        def _try_connect(self):
            try:
                if self._bus is None:
                    self._bus = SystemMessageBus()
                self._proxy = self._bus.get_proxy(BUS_NAME, OBJECT_PATH)
                self._proxy.Tick.connect(self._on_tick)
                self._proxy.EmergencyTriggered.connect(self._on_emergency)
                self._proxy.PropertiesChanged.connect(self._on_props)
                self.connected.emit(True)
                self._reconnect.stop()
            except DBusError as e:
                log.warning("daemon not reachable: %s", e)
                self.connected.emit(False)

        def _on_tick(self, temps, fans, level):
            self.tickReceived.emit(translate_tick(temps, fans, level))

        def _on_emergency(self, temp, sensor):
            self.emergency.emit(float(temp), str(sensor))

        def _on_props(self, iface, changed, invalidated):
            self.propertiesChanged.emit(dict(changed))

        def get(self, name: str):
            if self._proxy is None:
                return None
            return getattr(self._proxy, name)

        def set_mode(self, mode: str): self._proxy.SetMode(mode)
        def set_curve(self, points, sensors): self._proxy.SetCurve(points, sensors)
        def set_manual_level(self, lvl: str): self._proxy.SetManualLevel(lvl)
        def set_failsafe_temp(self, t: float): self._proxy.SetFailsafeTemp(t)
        def reload_config(self): self._proxy.ReloadConfig()

    return Client(parent)
```

- [ ] **Step 4: Tests laufen lassen — erwartet PASS**

Run: `.venv/bin/python -m pytest gui/tests/test_dbus_client.py -q`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add gui/src/tpfan_gui/ipc gui/tests/test_dbus_client.py
git commit -m "feat(gui): dbus client with Qt signal translation"
```

---

## Phase 10 — GUI: Views

### Task 10.1: `views/dashboard.py` — Live-Anzeige

**Files:**
- Create: `gui/src/tpfan_gui/views/__init__.py`
- Create: `gui/src/tpfan_gui/views/dashboard.py`
- Create: `gui/tests/test_dashboard.py`

- [ ] **Step 1: Test schreiben (pytest-qt)**

```python
# gui/tests/test_dashboard.py
from __future__ import annotations
import pytest

pytest.importorskip("pytestqt")


def test_dashboard_updates_with_tick(qtbot):
    from tpfan_gui.ipc.dbus_client import TickPayload
    from tpfan_gui.views.dashboard import Dashboard
    d = Dashboard()
    qtbot.addWidget(d)
    payload = TickPayload(
        temps={"CPU": 45.5, "GPU": 50.0},
        fans=[(2200, "auto"), (2100, "auto")],
        level="auto",
    )
    d.apply_tick(payload)
    assert "45.5" in d.cpu_label.text()
    assert "50.0" in d.gpu_label.text()
    assert "2200" in d.fan1_label.text()
    assert "auto" in d.level_label.text().lower()
```

- [ ] **Step 2: Test laufen lassen — erwartet FAIL**

Run: `.venv/bin/python -m pytest gui/tests/test_dashboard.py -q`
Expected: FAIL

- [ ] **Step 3: `views/dashboard.py` implementieren**

```python
# gui/src/tpfan_gui/views/__init__.py
```

```python
# gui/src/tpfan_gui/views/dashboard.py
from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QGridLayout, QLabel
from ..ipc.dbus_client import TickPayload


class Dashboard(QWidget):
    SENSOR_ORDER = ["CPU", "GPU", "NVMe", "RAM", "WLAN", "MB-CPU", "MB-GPU", "ACPI"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._labels: dict[str, QLabel] = {}
        grid = QGridLayout(self)
        for row, name in enumerate(self.SENSOR_ORDER):
            grid.addWidget(QLabel(name + ":"), row, 0)
            v = QLabel("--")
            grid.addWidget(v, row, 1)
            self._labels[name] = v
        self.cpu_label = self._labels["CPU"]
        self.gpu_label = self._labels["GPU"]
        self.fan1_label = QLabel("--")
        self.fan2_label = QLabel("--")
        self.level_label = QLabel("--")
        row = len(self.SENSOR_ORDER)
        grid.addWidget(QLabel("Fan 1 RPM:"), row, 0); grid.addWidget(self.fan1_label, row, 1); row += 1
        grid.addWidget(QLabel("Fan 2 RPM:"), row, 0); grid.addWidget(self.fan2_label, row, 1); row += 1
        grid.addWidget(QLabel("Level:"),     row, 0); grid.addWidget(self.level_label, row, 1)

    def apply_tick(self, p: TickPayload) -> None:
        for name, lbl in self._labels.items():
            v = p.temps.get(name)
            lbl.setText(f"{v:.1f} °C" if v is not None else "--")
        if len(p.fans) >= 1:
            self.fan1_label.setText(f"{p.fans[0][0]} ({p.fans[0][1]})")
        if len(p.fans) >= 2:
            self.fan2_label.setText(f"{p.fans[1][0]} ({p.fans[1][1]})")
        self.level_label.setText(p.level)
```

- [ ] **Step 4: Test laufen lassen — erwartet PASS**

Run: `.venv/bin/python -m pytest gui/tests/test_dashboard.py -q`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add gui/src/tpfan_gui/views gui/tests/test_dashboard.py
git commit -m "feat(gui): dashboard view with live sensor labels"
```

### Task 10.2: `views/history.py` — Ringpuffer 10 min, mehrere Linien

**Files:**
- Create: `gui/src/tpfan_gui/views/history.py`
- Create: `gui/tests/test_history.py`

- [ ] **Step 1: Test schreiben (reine Logik, kein Qt)**

```python
# gui/tests/test_history.py
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
```

- [ ] **Step 2: Test laufen lassen — erwartet FAIL**

Run: `.venv/bin/python -m pytest gui/tests/test_history.py -q`
Expected: FAIL

- [ ] **Step 3: `history.py` implementieren**

```python
# gui/src/tpfan_gui/views/history.py
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
```

- [ ] **Step 4: Tests laufen lassen — erwartet PASS**

Run: `.venv/bin/python -m pytest gui/tests/test_history.py -q`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add gui/src/tpfan_gui/views/history.py gui/tests/test_history.py
git commit -m "feat(gui): history ring buffer and pyqtgraph plot"
```

### Task 10.3: `views/curve_editor.py` — Editor mit ziehbaren Punkten

**Files:**
- Create: `gui/src/tpfan_gui/views/curve_editor.py`
- Create: `gui/tests/test_curve_editor.py`

Kernlogik: `CurveModel` mit add/remove/move-Operationen, Validierung (≥ 2 Punkte, monoton, range). Die pyqtgraph-Interaktion ist dünner View-Layer; Tests fokussieren das Modell.

- [ ] **Step 1: Test schreiben (Logik)**

```python
# gui/tests/test_curve_editor.py
from __future__ import annotations
import pytest
from tpfan_gui.views.curve_editor import CurveModel


def test_add_point_sorts_and_validates():
    m = CurveModel(points=[(40.0, 0), (80.0, 7)])
    m.add(60.0, 4)
    assert m.points == [(40.0, 0), (60.0, 4), (80.0, 7)]


def test_remove_keeps_minimum_two_points():
    m = CurveModel(points=[(40.0, 0), (80.0, 7)])
    with pytest.raises(ValueError):
        m.remove(0)
    m.add(60.0, 4)
    m.remove(1)
    assert m.points == [(40.0, 0), (80.0, 7)]


def test_move_clamps_to_range_and_keeps_monotonic():
    m = CurveModel(points=[(40.0, 0), (60.0, 4), (80.0, 7)])
    new = m.move(1, 35.0, 4)
    assert new[0] >= 40.0
    ts = [p[0] for p in m.points]
    assert ts == sorted(ts)


def test_move_clamps_level_to_0_7():
    m = CurveModel(points=[(40.0, 0), (80.0, 7)])
    m.add(60.0, 4)
    new = m.move(1, 60.0, 9)
    assert new[1] == 7
    new = m.move(1, 60.0, -2)
    assert new[1] == 0
```

- [ ] **Step 2: Test laufen lassen — erwartet FAIL**

Run: `.venv/bin/python -m pytest gui/tests/test_curve_editor.py -q`
Expected: FAIL

- [ ] **Step 3: `curve_editor.py` implementieren**

```python
# gui/src/tpfan_gui/views/curve_editor.py
from __future__ import annotations
from dataclasses import dataclass, field

EPS = 0.5


@dataclass
class CurveModel:
    points: list[tuple[float, int]] = field(default_factory=list)
    t_min: float = 20.0
    t_max: float = 110.0

    def add(self, t: float, level: int) -> None:
        self.points.append((float(t), max(0, min(7, int(level)))))
        self.points.sort(key=lambda p: p[0])

    def remove(self, index: int) -> None:
        if len(self.points) <= 2:
            raise ValueError("curve must keep at least 2 points")
        del self.points[index]

    def move(self, index: int, t: float, level: float) -> tuple[float, int]:
        t = max(self.t_min, min(self.t_max, float(t)))
        lvl = max(0, min(7, int(round(level))))
        left = self.points[index - 1][0] + EPS if index > 0 else self.t_min
        right = self.points[index + 1][0] - EPS if index < len(self.points) - 1 else self.t_max
        t = max(left, min(right, t))
        self.points[index] = (t, lvl)
        return self.points[index]


def make_widget(model: CurveModel, on_change, parent=None):
    """on_change(points) wird gerufen, wenn der User loslässt."""
    import pyqtgraph as pg
    from PyQt6.QtWidgets import QWidget, QVBoxLayout

    class CurveEditor(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            lay = QVBoxLayout(self)
            self.plot = pg.PlotWidget()
            self.plot.setXRange(30, 95)
            self.plot.setYRange(0, 7)
            self.plot.setLabel("bottom", "°C")
            self.plot.setLabel("left", "Level")
            lay.addWidget(self.plot)
            self.scatter = pg.ScatterPlotItem(size=12)
            self.line = pg.PlotCurveItem()
            self.plot.addItem(self.line)
            self.plot.addItem(self.scatter)
            self.refresh()

        def refresh(self):
            ts = [p[0] for p in model.points]
            ls = [p[1] for p in model.points]
            self.scatter.setData(x=ts, y=ls)
            self.line.setData(x=ts, y=ls)

        def commit(self):
            on_change(list(model.points))

    return CurveEditor(parent)
```

- [ ] **Step 4: Tests laufen lassen — erwartet PASS**

Run: `.venv/bin/python -m pytest gui/tests/test_curve_editor.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add gui/src/tpfan_gui/views/curve_editor.py gui/tests/test_curve_editor.py
git commit -m "feat(gui): curve editor model with monotonic add/move/remove"
```

### Task 10.4: `views/modes.py` — Mode/Profil/Failsafe Panel

**Files:**
- Create: `gui/src/tpfan_gui/views/modes.py`
- Create: `gui/tests/test_modes.py`

- [ ] **Step 1: Test schreiben**

```python
# gui/tests/test_modes.py
from __future__ import annotations
import pytest

pytest.importorskip("pytestqt")


def test_mode_buttons_emit_signal(qtbot):
    from tpfan_gui.views.modes import ModesPanel
    p = ModesPanel(profiles=["quiet", "balanced", "performance"])
    qtbot.addWidget(p)

    with qtbot.waitSignal(p.modeRequested, timeout=500) as blocker:
        p.auto_btn.click()
    assert blocker.args == ["auto"]

    with qtbot.waitSignal(p.modeRequested, timeout=500) as blocker:
        p.curve_btn.click()
    assert blocker.args == ["curve"]


def test_failsafe_spinbox_emits(qtbot):
    from tpfan_gui.views.modes import ModesPanel
    p = ModesPanel(profiles=[])
    qtbot.addWidget(p)
    p.failsafe_spin.setValue(85.0)
    with qtbot.waitSignal(p.failsafeRequested, timeout=500) as blocker:
        p.failsafe_spin.editingFinished.emit()
    assert blocker.args == [85.0]


def test_profile_change_emits_profile_mode(qtbot):
    from tpfan_gui.views.modes import ModesPanel
    p = ModesPanel(profiles=["quiet", "balanced"])
    qtbot.addWidget(p)
    p.profile_combo.setCurrentText("quiet")
    with qtbot.waitSignal(p.modeRequested, timeout=500) as blocker:
        p.apply_profile_btn.click()
    assert blocker.args == ["profile:quiet"]
```

- [ ] **Step 2: Test laufen lassen — erwartet FAIL**

Run: `.venv/bin/python -m pytest gui/tests/test_modes.py -q`
Expected: FAIL

- [ ] **Step 3: `modes.py` implementieren**

```python
# gui/src/tpfan_gui/views/modes.py
from __future__ import annotations
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
                              QDoubleSpinBox, QComboBox, QLabel, QGroupBox)
from PyQt6.QtCore import pyqtSignal


class ModesPanel(QWidget):
    modeRequested = pyqtSignal(str)
    manualLevelRequested = pyqtSignal(str)
    failsafeRequested = pyqtSignal(float)

    def __init__(self, profiles: list[str], parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)

        gb_modes = QGroupBox("Modus")
        ml = QHBoxLayout(gb_modes)
        self.auto_btn   = QPushButton("Auto")
        self.curve_btn  = QPushButton("Kurve")
        self.manual_btn = QPushButton("Manuell")
        for b, name in [(self.auto_btn, "auto"), (self.curve_btn, "curve"), (self.manual_btn, "manual")]:
            b.clicked.connect(lambda _=False, n=name: self.modeRequested.emit(n))
            ml.addWidget(b)
        root.addWidget(gb_modes)

        gb_man = QGroupBox("Manuelles Level")
        manl = QHBoxLayout(gb_man)
        for lvl in ["0", "1", "2", "3", "4", "5", "6", "7", "disengaged"]:
            b = QPushButton(lvl)
            b.clicked.connect(lambda _=False, v=lvl: self.manualLevelRequested.emit(v))
            manl.addWidget(b)
        root.addWidget(gb_man)

        gb_prof = QGroupBox("Profil")
        pl = QHBoxLayout(gb_prof)
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(profiles)
        self.apply_profile_btn = QPushButton("Anwenden")
        self.apply_profile_btn.clicked.connect(self._on_apply_profile)
        pl.addWidget(self.profile_combo); pl.addWidget(self.apply_profile_btn)
        root.addWidget(gb_prof)

        gb_fs = QGroupBox("Failsafe (°C)")
        fl = QHBoxLayout(gb_fs)
        self.failsafe_spin = QDoubleSpinBox()
        self.failsafe_spin.setRange(40.0, 110.0)
        self.failsafe_spin.setDecimals(1)
        self.failsafe_spin.setValue(95.0)
        self.failsafe_spin.editingFinished.connect(
            lambda: self.failsafeRequested.emit(self.failsafe_spin.value()))
        fl.addWidget(QLabel("Schwelle:")); fl.addWidget(self.failsafe_spin)
        root.addWidget(gb_fs)

    def _on_apply_profile(self):
        name = self.profile_combo.currentText()
        if name:
            self.modeRequested.emit(f"profile:{name}")
```

- [ ] **Step 4: Tests laufen lassen — erwartet PASS**

Run: `.venv/bin/python -m pytest gui/tests/test_modes.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add gui/src/tpfan_gui/views/modes.py gui/tests/test_modes.py
git commit -m "feat(gui): modes panel with mode/profile/failsafe controls"
```

---

## Phase 11 — GUI: Main-Fenster und Tray

### Task 11.1: `__main__.py` und `main_window.py`

**Files:**
- Create: `gui/src/tpfan_gui/__main__.py`
- Create: `gui/src/tpfan_gui/main_window.py`

- [ ] **Step 1: `main_window.py` schreiben**

```python
# gui/src/tpfan_gui/main_window.py
from __future__ import annotations
from PyQt6.QtWidgets import QMainWindow, QTabWidget, QStatusBar, QMessageBox

from .ipc.dbus_client import TickPayload
from .views.dashboard import Dashboard
from .views.history import make_widget as make_history
from .views.curve_editor import CurveModel, make_widget as make_curve_editor
from .views.modes import ModesPanel


class MainWindow(QMainWindow):
    def __init__(self, client):
        super().__init__()
        self.setWindowTitle("tpfan")
        self.client = client

        self.curve_model = CurveModel(points=[(40.0, 0), (55.0, 2), (70.0, 4), (80.0, 7)])
        self.dashboard = Dashboard()
        self.history = make_history()
        self.curve_editor = make_curve_editor(self.curve_model, self._send_curve)
        self.modes = ModesPanel(profiles=["quiet", "balanced", "performance"])

        tabs = QTabWidget()
        tabs.addTab(self.dashboard, "Übersicht")
        tabs.addTab(self.history, "Verlauf")
        tabs.addTab(self.curve_editor, "Kurve")
        tabs.addTab(self.modes, "Modus")
        self.setCentralWidget(tabs)
        self.setStatusBar(QStatusBar())

        client.tickReceived.connect(self._on_tick)
        client.emergency.connect(self._on_emergency)
        client.connected.connect(self._on_connected)

        self.modes.modeRequested.connect(self._wrap(self.client.set_mode))
        self.modes.manualLevelRequested.connect(self._wrap(self.client.set_manual_level))
        self.modes.failsafeRequested.connect(self._wrap(self.client.set_failsafe_temp))

        self._t0 = None

    def _wrap(self, fn):
        def call(*args):
            try:
                fn(*args)
            except Exception as e:
                QMessageBox.warning(self, "tpfan", f"Fehler: {e}")
        return call

    def _send_curve(self, points):
        sensors = ["CPU", "GPU", "NVMe"]
        try:
            self.client.set_curve(points, sensors)
        except Exception as e:
            QMessageBox.warning(self, "tpfan", f"Kurve nicht übernommen: {e}")

    def _on_tick(self, payload: TickPayload):
        self.dashboard.apply_tick(payload)
        import time
        t = time.monotonic()
        if self._t0 is None:
            self._t0 = t
        self.history.append(t - self._t0, payload.temps)

    def _on_emergency(self, temp: float, sensor: str):
        QMessageBox.critical(self, "Failsafe ausgelöst",
                             f"Failsafe wegen {sensor} bei {temp:.1f} °C aktiviert.")

    def _on_connected(self, ok: bool):
        self.statusBar().showMessage("Verbunden" if ok else "Daemon nicht erreichbar")
```

- [ ] **Step 2: `__main__.py` schreiben**

```python
# gui/src/tpfan_gui/__main__.py
from __future__ import annotations
import sys
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon

from .ipc.dbus_client import make_client
from .main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    client = make_client()
    win = MainWindow(client)
    win.resize(700, 500)

    tray = QSystemTrayIcon(QIcon.fromTheme("fan"))
    menu = QMenu()
    menu.addAction("Öffnen").triggered.connect(win.show)
    menu.addAction("Beenden").triggered.connect(app.quit)
    tray.setContextMenu(menu)
    tray.show()
    win.show()

    run_qt_loop = getattr(app, "exec")
    return run_qt_loop()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Syntax-Check**

Run: `.venv/bin/python -c "import tpfan_gui.main_window, tpfan_gui.__main__"`
Expected: kein Output (oder reine PyQt6-Importwarnungen, falls headless).

- [ ] **Step 4: Commit**

```bash
git add gui/src/tpfan_gui/__main__.py gui/src/tpfan_gui/main_window.py
git commit -m "feat(gui): main window with tabs, tray and signal wiring"
```

---

## Phase 12 — Manuelle Tests und Erfolgskriterien

### Task 12.1: `docs/manual-test.md`

**Files:**
- Create: `docs/manual-test.md`

- [ ] **Step 1: Checkliste schreiben**

```markdown
# tpfan — Manuelle Test-Checkliste

Voraussetzungen:
- Fedora 44 oder kompatibles System auf einem ThinkPad E14 Gen 7.
- `sudo make install` ausgeführt.
- `sudo modprobe -r thinkpad_acpi && sudo modprobe thinkpad_acpi` oder Reboot,
  damit `fan_control=1` aktiv ist.
- `systemctl enable --now tpfan-daemon.service`

Smoke-Tests:

- [ ] `systemctl status tpfan-daemon` zeigt `active (running)`.
- [ ] `journalctl -u tpfan-daemon -n 20 --no-pager` zeigt „READY=1" und keine Tracebacks.
- [ ] `busctl --system introspect org.tpfan1 /org/tpfan1` listet `Sensors`, `Fans`, `Mode`, Methoden.
- [ ] `tpfan-gui` startet, zeigt Live-Werte für CPU/GPU/NVMe/RAM/WLAN (Latenz < 1 s).
- [ ] Modus „Auto" → `cat /proc/acpi/ibm/fan` zeigt `level: auto`.
- [ ] Modus „Manuell" → Level 5 klicken → `level: 5`.
- [ ] Modus „Kurve" mit CPU-Last (`stress-ng --cpu 4 --timeout 60`) → Level steigt sichtbar.
- [ ] Kurveneditor: Punkt verschieben → „Anwenden" → polkit-Prompt → Wirkung sichtbar.
- [ ] Profil „Quiet" anwenden → Lüfter bei Idle leiser.
- [ ] Failsafe-Test: Failsafe auf 50 °C setzen, CPU-Last erzeugen → GUI-Dialog erscheint,
  `level: disengaged` sichtbar, journald loggt `EmergencyTriggered`.
- [ ] `systemctl stop tpfan-daemon` → nach Stop bleibt `level: auto`.
- [ ] GUI ohne Daemon: GUI zeigt Statusbar „Daemon nicht erreichbar", reconnects beim Start.
```

- [ ] **Step 2: Commit**

```bash
git add docs/manual-test.md
git commit -m "docs: manual test checklist for end-to-end verification"
```

### Task 12.2: README erweitern

**Files:**
- Modify: `README.md`

- [ ] **Step 1: README mit Installations- und Bedienungshinweisen erweitern**

```markdown
# tpfan

Lüfter-Steuerung und Temperatur-Anzeige für ThinkPad E14 Gen 7 unter Linux.

Architektur und API siehe `docs/superpowers/specs/2026-05-10-tpfan-design.md`.
Implementierungsplan siehe `docs/superpowers/plans/2026-05-13-tpfan-implementation.md`.

## Installation

    # Voraussetzungen (Fedora):
    sudo dnf install python3-pip python3-gobject dbus-daemon polkit
    # einmaliges Modul-Setup:
    sudo cp packaging/tpfan-modprobe.conf /etc/modprobe.d/tpfan.conf
    sudo modprobe -r thinkpad_acpi && sudo modprobe thinkpad_acpi

    # System-Install:
    sudo make install
    sudo systemctl enable --now tpfan-daemon

    # GUI starten:
    tpfan-gui

## Entwicklung

    make dev           # editable installs in .venv
    make test          # alle Unit-Tests
    make test-daemon   # nur Daemon
    make test-gui      # nur GUI

## Logs

    journalctl -u tpfan-daemon -f         # Daemon
    TPFAN_LOG=debug tpfan-gui             # GUI mit Debug-Ausgabe

## Manueller End-to-End-Test

Siehe `docs/manual-test.md`.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: expand README with install, usage and dev sections"
```

---

## Phase 13 — Abschluss

### Task 13.1: Gesamtsuite und Coverage prüfen

- [ ] **Step 1: Alle Tests laufen lassen**

Run: `make test`
Expected: alle Tests grün; Skips nur für D-Bus-Test ohne `dbus-daemon` und Qt-Tests ohne `pytest-qt`.

- [ ] **Step 2: Coverage-Report**

Run: `.venv/bin/python -m pytest daemon/tests --cov=tpfan_daemon.hw --cov=tpfan_daemon.control --cov=tpfan_daemon.config --cov-report=term -q`
Expected: Jeweils ≥ 90 % für `hw/`, `control/`, `config.py`. Andernfalls fehlende Pfade durch Tests abdecken.

- [ ] **Step 3: Manuelle Test-Checkliste auf echtem Gerät durchgehen**

Folge `docs/manual-test.md`. Hake jeden Punkt ab. Bei Abweichungen Fix-Commit anlegen.

- [ ] **Step 4: Optional — Abschluss-Commit falls Doku-Änderungen nötig**

```bash
git add -A
git commit -m "chore: address findings from manual test pass"
```

- [ ] **Step 5: Skill-Anwendung: `superpowers:finishing-a-development-branch` für Integrations-Entscheid**

---

## Selbstkontrolle (vom Plan-Autor)

**Spec-Coverage:**
- §2 Hardware-Schnittstellen: Phase 1 (sensors), Phase 1.2 (fan) ✓
- §3/§4.1 Daemon-Module: alle Module abgedeckt (sensors, fan, curve, loop, dbus_service, config, daemon.py, __main__) ✓
- §4.2 GUI-Module: dashboard, curve_editor, history, modes, dbus_client, __main__/main_window ✓
- §4.3 System-Integration: Phase 8 deckt systemd, D-Bus, polkit, modprobe, desktop ✓
- §5 D-Bus-API: alle Properties (inkl. `CurveSensors`), Methoden, Signale in Phase 5.1 ✓
- §6 Datenfluss: Phase 4.1 implementiert Failsafe→Auto→Manual→Curve in dieser Reihenfolge ✓
- §7 Kurveneditor: Modell in Phase 10.3 (getestet), pyqtgraph-View dünn — über Phase 12 manuell zu validieren ✓
- §8 Config: Phase 2.1 atomic write, validate ✓
- §9 Fehlerbehandlung: Retries (Phase 1.2), Failsafe (Phase 4.1), Disconnect-Reconnect (Phase 9.1), Validierung (Phase 5.2/6.1) ✓
- §10 Tests: pytest in jeder Phase; D-Bus-Test in Phase 5.1; Integration in Phase 7.1 ✓
- §11 Layout: Phase 0.1–0.3 + Packaging in Phase 8 ✓
- §12 Abhängigkeiten: in pyproject.toml-Dateien ✓
- §14 Erfolgskriterien: 1 (systemd, Phase 8), 2 (GUI Latenz, Phase 10.1+11), 3 (Kurveneditor, Phase 10.3),
  4 (Mode-Buttons, Phase 10.4), 5 (Failsafe, Phase 4.1+7.1), 6 (auto bei Stop, Phase 6.2 `__main__`),
  7 (Coverage, Phase 13.1) ✓

**Placeholder-Scan:** keine TBD/TODO/„später"-Steps. pyqtgraph-Maushandling im Kurveneditor ist bewusst dünn — die Geschäftslogik liegt im `CurveModel` und ist getestet; die View-Interaktion wird im manuellen Smoke-Test (Phase 12) validiert.

**Typ-Konsistenz:** `CurveCfg.points` ist `tuple[tuple[float,int],...]`; D-Bus liefert `List[Tuple[Double, Byte]]`, Konvertierung in Phase 5.1 und Phase 6.1 (`_validate_points`). `Mode` ist String inkl. `profile:<name>`, konsistent in Phase 4.1, 5.1, 6.1, 10.4. `_lvl_to_int` (Phase 6.2) und `_level_int_to_str` (Phase 9.1) sind komplementär (0xFF ⇔ "auto").

---

**Plan abgeschlossen.** Speicherort: `docs/superpowers/plans/2026-05-13-tpfan-implementation.md`.
