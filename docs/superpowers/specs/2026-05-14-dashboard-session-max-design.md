# Dashboard Session-Max — Design

## Ziel

Auf dem Übersichts-Tab erscheint hinter jedem aktuellen Temperaturwert das Session-Maximum (höchster seit GUI-Start beobachteter Wert).

## Format

`42.5 °C  (max 67.3 °C)` im bestehenden Wertelabel — keine zusätzliche Grid-Spalte.

Solange für einen Sensor noch kein Wert eingegangen ist, bleibt das Label `--` ohne Max-Suffix.

## Datenmodell

`Dashboard._max: dict[str, float]` (leer bei `__init__`). Per `apply_tick` wird für jeden im `TickPayload.temps` enthaltenen Sensor `_max[name] = max(_max.get(name, v), v)` aktualisiert. Lebensdauer = Widget-Lebensdauer = GUI-Session.

## Scope-Abgrenzung

- Nur Temperaturen, keine Fan-RPM, kein Level.
- Kein Min-Wert.
- Kein manueller Reset-Button.
- Keine Persistenz über GUI-Neustarts hinweg.

## Tests

`gui/tests/test_dashboard.py` (Datei existiert): ein Test mit zwei `apply_tick`-Aufrufen (CPU steigt 50→60, dann fällt 60→55) und Assert auf den Label-Text, dass `(max 60.0` enthalten ist. Zweiter Test: vor jeglichem Tick zeigt das Label `--` ohne Max-Suffix.
