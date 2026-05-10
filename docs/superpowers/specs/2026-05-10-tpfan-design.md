# tpfan — Design Spec

**Datum:** 2026-05-10
**Zielgerät:** Lenovo ThinkPad E14 Gen 7 (21T0CTO1WW), Fedora 44, Kernel 7.0.4
**Status:** Design approved, bereit für Implementierungsplan

## 1. Ziel

Ein kleines Linux-Tool zur Anzeige aller relevanten Temperaturen und zur Steuerung
der Lüfter eines ThinkPad E14 Gen 7. Mit benutzerdefinierter Lüfterkurve,
Profilen, Failsafe und Live-Verlaufsanzeige.

## 2. Hardware-Schnittstellen (auf dem Zielgerät verifiziert)

- **Temperaturen:** `/sys/class/hwmon/*` über existierende Kernel-Treiber
  - `k10temp` → CPU (Tctl)
  - `amdgpu` → iGPU (edge)
  - `nvme` → NVMe (Composite + Sensor 1/2)
  - `thinkpad` → Mainboard-Thermozonen (CPU/GPU/temp3-8)
  - `spd5118` → RAM
  - `mt7921_phy0` → WLAN
  - `acpitz` → ACPI Thermal Zone (Backup)
- **Lüfter-Lesen:** `hwmon9/fan1_input`, `hwmon9/fan2_input` (RPM)
- **Lüfter-Steuerung:** `/proc/acpi/ibm/fan` mit
  Levels `0..7`, `auto`, `disengaged` (= full-speed). Erfordert `thinkpad_acpi`
  Modul mit `fan_control=1`.

## 3. Architektur

```
┌──────────────────┐   D-Bus (System-Bus)   ┌──────────────────┐
│  GUI (PyQt6)     │◄─────────────────────►│  Daemon (Python) │
│  user session    │  org.tpfan1            │  systemd, root   │
└──────────────────┘                        └────────┬─────────┘
                                                     │
                                            ┌────────┴─────────┐
                                            │ HW-Abstraktion   │
                                            ├──────────────────┤
                                            │ /sys/class/hwmon │
                                            │ /proc/acpi/ibm/  │
                                            └──────────────────┘
```

**Trennung:** Daemon als root-systemd-Unit hält die Regelschleife stabil,
auch wenn keine GUI läuft. GUI ist reiner D-Bus-Client. PolicyKit autorisiert
schreibende Operationen.

## 4. Komponenten

### 4.1 `tpfan-daemon` (Python, root)

| Modul | Verantwortung |
|-------|---------------|
| `hw/sensors.py` | hwmon-Discovery beim Start, semantisches Mapping (CPU/GPU/NVMe/RAM/WLAN/Mainboard), Lesen mit Fehlertoleranz |
| `hw/fan.py` | Wrapper um `/proc/acpi/ibm/fan` (Lesen `level`/`speed`, Schreiben `level X`) |
| `control/curve.py` | Kurven-Engine: lineare Interpolation + Hysterese (3 °C Rückfall-Schwelle) |
| `control/loop.py` | 1 Hz-Regelschleife, Modus-Logik, Failsafe |
| `ipc/dbus_service.py` | Export von `org.tpfan1` auf System-Bus |
| `config.py` | TOML-Konfig in `/etc/tpfan/config.toml`, atomic write |
| `__main__.py` | systemd-Watchdog-Ping, Signal-Handling, Bootstrap |

### 4.2 `tpfan-gui` (PyQt6, user)

| Modul | Verantwortung |
|-------|---------------|
| `views/dashboard.py` | Live-Anzeige aller Temperaturen, RPM, aktueller Modus/Level |
| `views/curve_editor.py` | pyqtgraph-Plot, ziehbare Punkte, Rechtsklick add/delete |
| `views/history.py` | Ringpuffer 10 min, mehrere Sensorlinien |
| `views/modes.py` | Buttons Auto/Curve/Manual, Profil-Auswahl, Failsafe-Spinbox |
| `ipc/dbus_client.py` | System-Bus-Wrapper, D-Bus-Signale → Qt-Signals |
| `main.py` | App, QSystemTrayIcon, Hauptfenster |

### 4.3 System-Integration

- **systemd:** `tpfan-daemon.service` (`Type=dbus`, `WatchdogSec=10`, `Restart=on-failure`)
- **D-Bus:** Service-Datei `org.tpfan1.service`, Bus-Policy `org.tpfan1.conf`
- **PolicyKit:** `org.tpfan1.policy` (Admin-Auth einmalig pro Session für `Set*`-Methoden)
- **modprobe:** `/etc/modprobe.d/tpfan.conf` mit `options thinkpad_acpi fan_control=1`
- **Desktop:** `tpfan-gui.desktop` für Anwendungsmenü

## 5. D-Bus-API

Service: `org.tpfan1`, Pfad `/org/tpfan1`.

### Properties (read-only, `PropertiesChanged`-Signal)
- `Sensors: a{s(dss)}` — `name → (value_celsius, label, source)`
- `Fans: a(uu)` — `[(rpm, level), ...]` für fan1, fan2
- `Mode: s` — `"auto" | "curve" | "manual" | "profile:quiet" | "profile:balanced" | "profile:performance"`
- `CurrentLevel: s` — `"0".."7" | "auto" | "disengaged"`
- `Curve: a(dy)` — `[(temp_c, level), ...]`
- `FailsafeTemp: d`
- `DaemonVersion: s`

### Methoden (PolicyKit-geschützt)
- `SetMode(s mode)`
- `SetCurve(a(dy) points)` — validiert: ≥2 Punkte, Temps 20–110 °C monoton steigend, Level 0–7
- `SetManualLevel(s level)` — nur in `mode=manual`
- `SetFailsafeTemp(d temp)`
- `ReloadConfig()`

### Signale
- `Tick(a{sd} temps, a(uu) fans, s level)` — 1 Hz, Push-Updates
- `EmergencyTriggered(d temp, s sensor)` — Failsafe ausgelöst

## 6. Datenfluss (1 Hz Loop)

```
read_all_sensors() ─► temps
read_fan() ─► (rpm1, rpm2, current_level)

if any temp ≥ failsafe_temp:
    write_fan("disengaged"); emit EmergencyTriggered
elif mode == "auto":
    write_fan("auto")
elif mode == "manual":
    write_fan(manual_level)
elif mode == "curve" or "profile:*":
    curve = active_curve()
    t = max(temps[s] for s in curve.sensors if s in temps)
    target = interpolate(curve.points, t, hysteresis=3°C, prev=current_level)
    if target != current_level:
        write_fan(target)

emit Tick(temps, fans, level)
```

**Hysterese:** Bei steigender Temperatur folgt das Level direkt der Kurve.
Bei fallender Temperatur wird ein Level erst zurückgenommen, wenn die
Temperatur 3 °C unter dem Schwellpunkt liegt — verhindert Pumpen.

## 7. Kurveneditor (UI)

- pyqtgraph-Plot, X = 30–95 °C, Y = Level 0–7
- Punkte als ziehbare ScatterPlot-Items
- Linksklick auf Punkt + drag → verschieben (mit Snap auf Y-Integer)
- Rechtsklick auf Plot → „Punkt hinzufügen"
- Rechtsklick auf Punkt → „Punkt löschen"
- Beim Loslassen: Validierung, Sortierung, `SetCurve` über D-Bus
- Eingangs-Sensoren via Checkboxen (Default: CPU, GPU, NVMe)

## 8. Konfiguration

`/etc/tpfan/config.toml` ist Single-Source-of-Truth für den Daemon:

```toml
mode = "curve"
manual_level = "3"
failsafe_temp = 95.0

[curve]
sensors = ["CPU", "GPU", "NVMe"]
points = [[40, 0], [55, 2], [70, 4], [80, 7]]

[profiles.quiet]
points = [[50, 0], [65, 1], [75, 3], [85, 7]]

[profiles.balanced]
points = [[40, 0], [55, 2], [70, 4], [80, 7]]

[profiles.performance]
points = [[35, 1], [50, 3], [65, 5], [75, 7]]
```

Atomic Write (tmp + rename), Lock-Datei `/run/tpfan.lock`.

## 9. Fehlerbehandlung & Sicherheit

- **EC-Voraussetzung:** Daemon prüft beim Start, ob `/proc/acpi/ibm/fan`
  schreibbar ist. Andernfalls → Log-Fehler, Daemon-Exit. Modprobe-Konfig
  ist Installations-Schritt.
- **Schreibfehler Fan:** 3 Retries à 100 ms; bei Dauerfehler → `mode=auto`
  zurückfallen, `EmergencyTriggered` mit Grund.
- **Sensor-Lesefehler:** Einzelne Sensoren werden übersprungen; wenn alle
  ausfallen → sofort `auto`.
- **Failsafe-Hierarchie:** (1) Temp ≥ failsafe → `disengaged`,
  (2) sonst Modus, (3) bei `SIGTERM` → `auto` zurücksetzen.
- **Watchdog:** systemd `WatchdogSec=10`. Bei Hang → systemd-Restart;
  zwischenzeitlich regelt EC mit `auto`.
- **GUI-Disconnect:** GUI zeigt „Daemon nicht erreichbar", reconnect alle 2 s.
- **Validierung:** Alle `Set*`-Methoden validieren Eingaben, geben D-Bus-Errors zurück.
- **Logging:** stdout/stderr → journald. Loglevel via `TPFAN_LOG=info|debug`.

## 10. Tests

- **Unit (`pytest`):**
  - `test_curve.py` — Interpolation, Hysterese, Edge-Cases (Temp unter erstem/über letztem Punkt)
  - `test_sensors.py` — tmpfs-Mock-hwmon-Tree, Discovery, Fehler-Robustheit
  - `test_config.py` — TOML round-trip, Validierung, atomic write
  - `test_fan.py` — gegen Fake-`/proc/acpi/ibm/fan`
- **Integration:** `test_loop.py` — Curve-Engine + Fake-HW, simulierte Temp-Verläufe
- **D-Bus:** `test_dbus.py` mit `dbus-daemon --session` als Test-Bus
- **Manuell:** Smoke-Test-Checkliste in `docs/manual-test.md` für GUI auf echtem Gerät
- **Coverage-Ziel:** `hw/`, `control/`, `config.py` ≥ 90 %; GUI manuell

## 11. Projekt-Layout

```
tpfan/
├── daemon/
│   ├── pyproject.toml
│   ├── src/tpfan_daemon/
│   │   ├── __main__.py
│   │   ├── hw/{sensors.py,fan.py}
│   │   ├── control/{curve.py,loop.py}
│   │   ├── ipc/dbus_service.py
│   │   └── config.py
│   └── tests/
├── gui/
│   ├── pyproject.toml
│   ├── src/tpfan_gui/
│   │   ├── __main__.py
│   │   ├── views/{dashboard.py,curve_editor.py,history.py,modes.py}
│   │   └── ipc/dbus_client.py
│   └── tests/
├── packaging/
│   ├── tpfan-daemon.service
│   ├── org.tpfan1.conf
│   ├── org.tpfan1.service
│   ├── org.tpfan1.policy
│   ├── tpfan-modprobe.conf
│   └── tpfan-gui.desktop
├── docs/
│   ├── superpowers/specs/2026-05-10-tpfan-design.md
│   └── manual-test.md
├── Makefile
└── README.md
```

## 12. Abhängigkeiten

- **Daemon:** `dasbus`, `tomllib` (stdlib ab Python 3.11)
- **GUI:** `PyQt6`, `pyqtgraph`, `dasbus`
- **System:** Python ≥ 3.11, systemd, polkit, `thinkpad_acpi` mit `fan_control=1`

## 13. Out-of-Scope (YAGNI)

- Kein Multi-User-Conflict-Resolution (letzter Set gewinnt)
- Keine Netzwerk-/Remote-Steuerung
- Kein automatisches Profil-Switching nach AC/Battery
- Keine i18n; Texte deutsch
- Keine Distro-Pakete (RPM/DEB) im ersten Wurf — nur `make install`

## 14. Erfolgskriterien

1. Daemon startet als systemd-Service und überlebt Crashes.
2. GUI zeigt alle aufgelisteten Sensoren live mit < 1 s Latenz.
3. Lüfterkurve mit ziehbaren Punkten editierbar; Änderung wirkt sofort.
4. Mode-Wechsel (Auto/Curve/Manual/Profile) per Button funktioniert.
5. Failsafe schaltet bei künstlich gesetztem niedrigem Threshold (z. B. 50 °C)
   nachweislich auf `disengaged`.
6. Bei Daemon-Stopp wird Lüfter zurück auf `auto` gesetzt — Firmware übernimmt.
7. Unit-Test-Coverage für `hw/`, `control/`, `config.py` ≥ 90 %.
