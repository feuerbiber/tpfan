# tpfan

Lüfter-Steuerung und Temperatur-Anzeige für ThinkPad E14 Gen 7 unter Linux.

Architektur und API siehe `docs/superpowers/specs/2026-05-10-tpfan-design.md`.
Implementierungsplan siehe `docs/superpowers/plans/2026-05-13-tpfan-implementation.md`.

## Installation

Komfort-Skript (Fedora-artige Distros):

    sudo ./scripts/install.sh

Das Skript installiert System-Abhängigkeiten (`dnf`), die Python-Pakete systemweit,
alle Packaging-Dateien (systemd, D-Bus, polkit, modprobe, Desktop-Entry), lädt
`thinkpad_acpi` mit `fan_control=1` neu und aktiviert den Service.

GUI starten:

    tpfan-gui

Deinstallation:

    sudo ./scripts/install.sh --uninstall

Manuell (falls nicht-Fedora oder feinere Kontrolle gewünscht):

    sudo dnf install python3-pip python3-gobject dbus-daemon polkit
    sudo /usr/bin/python3 -m pip install --break-system-packages ./daemon ./gui
    sudo make install
    sudo modprobe -r thinkpad_acpi && sudo modprobe thinkpad_acpi
    sudo systemctl enable --now tpfan-daemon

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
