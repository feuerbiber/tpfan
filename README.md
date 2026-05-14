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
