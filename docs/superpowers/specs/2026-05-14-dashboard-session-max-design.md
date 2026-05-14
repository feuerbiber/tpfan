# Dashboard Session-Max — Design

## Ziel

Auf dem Übersichts-Tab erscheint hinter jedem aktuellen Temperaturwert das Session-Maximum (höchster seit GUI-Start beobachteter Wert).

## Format

Eigene Tabellenspalte „Max" rechts neben „aktuell". Header-Zeile mit Spaltennamen über den Sensoren. Vor dem ersten Tick zeigen beide Spalten `--`. Wenn ein Sensor einmal beobachtet wurde, behält die Max-Spalte den höchsten Wert auch dann, wenn der Sensor in einem späteren Tick fehlt (aktuell-Spalte wird `--`, Max bleibt).

## Datenmodell

`Dashboard._max: dict[str, float]` (leer bei `__init__`); `Dashboard._max_labels: dict[str, QLabel]` pro Sensor. Per `apply_tick` wird für jeden im `TickPayload.temps` enthaltenen Sensor `_max[name] = max(_max.get(name, v), v)` aktualisiert und das Max-Label gesetzt. Lebensdauer = Widget-Lebensdauer = GUI-Session.

## Scope-Abgrenzung

- Nur Temperaturen, keine Fan-RPM, kein Level.
- Kein Min-Wert.
- Kein manueller Reset-Button.
- Keine Persistenz über GUI-Neustarts hinweg.

## Tests

`gui/tests/test_dashboard.py` (Datei existiert): Test mit drei `apply_tick`-Aufrufen (CPU 50 → 60 → 55), Assert auf `cpu_label == "55.0 °C"` und `_max_labels["CPU"] == "60.0 °C"`. Zweiter Test: vor jeglichem Tick zeigen beide Labels `--`.
