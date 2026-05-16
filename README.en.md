# tpfan

*Deutsche Version: [README.md](README.md).*

Fan control and temperature display for ThinkPad notebooks on Linux
(developed and tested on a ThinkPad E14 Gen 7). Drives the fan through
the `thinkpad_acpi` kernel module (`fan_control=1`) and ships a
Qt-based GUI with tray icon, status view, and fan-curve editor.

## Components

- **`tpfan-daemon`** — system service that reads temperatures and sets
  the fan level via `/proc/acpi/ibm/fan`. Exposes a D-Bus API
  (`org.tpfan1`, system bus).
- **`tpfan-gui`** — user-facing application with a main window and
  system tray. Talks to the daemon exclusively over D-Bus.
- **Packaging** — systemd service, D-Bus service and policy files,
  polkit action, modprobe snippet (`fan_control=1`), desktop entry, and
  icon.

## Requirements

- Linux with the `thinkpad_acpi` module (the installer reloads it with
  `fan_control=1`).
- Python ≥ 3.11.
- D-Bus system bus, polkit, PyGObject (`gi`, for the GUI integration).
- The installer handles required packages itself on Fedora/RHEL
  (`dnf`), Debian/Ubuntu/Mint (`apt`), and Arch/Manjaro (`pacman`):
  pip, venv, PyGObject, D-Bus, polkit.

## Installation

Convenience script (Fedora-, Debian-, and Arch-based distros):

    sudo ./scripts/install.sh

The script:

1. installs missing system dependencies via `dnf`, `apt`, or `pacman`
   (depending on the detected distro family),
2. creates a dedicated venv at `/opt/tpfan/venv`
   (`--system-site-packages`, so the system's `python3-gobject` stays
   usable) and installs `tpfan-daemon` + `tpfan-gui` into it,
3. copies all packaging files (systemd, D-Bus, polkit, modprobe,
   desktop entry, icon),
4. reloads `thinkpad_acpi` with `fan_control=1` (a reboot is required
   if the module is currently in use),
5. enables and starts `tpfan-daemon.service`,
6. runs a smoke check (systemd active, D-Bus name registered).

Launch the GUI:

    tpfan-gui

Uninstall (removes venv, packaging, config under `/etc/tpfan`, and
state under `/var/lib/tpfan`):

    sudo ./scripts/install.sh --uninstall

Installer environment variables:

- `TPFAN_PY` — alternative Python interpreter used to create the venv
  (default `/usr/bin/python3`).
- `TPFAN_VENV` — target directory of the venv (default
  `/opt/tpfan/venv`).

## Usage

- **Tray icon**: shows the current maximum temperature on a colored
  circle (green = levels 0–2, yellow = 3–5, red = 6–7/disengaged).
  Left-click opens or hides the window; right-click opens the menu
  with mode switching (Auto/Curve/Manual) and manual level selection.
- **Main window**: tabs for status, curve editor, and general
  settings.

## Logs

    journalctl -u tpfan-daemon -f         # daemon logs
    TPFAN_LOG=debug tpfan-gui             # GUI with debug output

## Development

    make dev           # editable installs in .venv
    make test          # all unit tests
    make test-daemon   # daemon only
    make test-gui      # GUI only

Architecture and API: `docs/superpowers/specs/2026-05-10-tpfan-design.md`.
Implementation plan: `docs/superpowers/plans/2026-05-13-tpfan-implementation.md`.
Manual end-to-end test: `docs/manual-test.md`.

## Origin

tpfan was built with [Claude Code](https://www.claude.com/product/claude-code)
(Anthropic) — design, implementation, tests, and packaging were all
produced in collaboration with the AI assistant.

## License

tpfan is released under the **GNU General Public License v3.0 or
later** (`GPL-3.0-or-later`). The full license text is in `LICENSE`.

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
    GNU General Public License for more details.
