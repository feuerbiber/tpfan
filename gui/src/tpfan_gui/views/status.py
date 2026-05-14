from __future__ import annotations
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QGroupBox,
                              QLabel, QTableWidget, QTableWidgetItem,
                              QPushButton, QHBoxLayout, QHeaderView)


def _fmt_curve(points: list) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for p in points:
        try:
            t = float(p[0])
            lvl = int(p[1])
            rows.append((f"{t:.1f} °C", str(lvl)))
        except (TypeError, ValueError, IndexError):
            continue
    return rows


class StatusView(QWidget):
    """Read-only Übersicht der aktuell gesetzten Daemon-Einstellungen."""

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self._client = client

        root = QVBoxLayout(self)

        gb_general = QGroupBox("Aktuelle Einstellungen")
        form = QFormLayout(gb_general)
        self.mode_lbl = QLabel("—")
        self.level_lbl = QLabel("—")
        self.failsafe_lbl = QLabel("—")
        self.version_lbl = QLabel("—")
        form.addRow("Modus:", self.mode_lbl)
        form.addRow("Aktueller Level:", self.level_lbl)
        form.addRow("Failsafe-Schwelle:", self.failsafe_lbl)
        form.addRow("Daemon-Version:", self.version_lbl)
        root.addWidget(gb_general)

        gb_curve = QGroupBox("Aktive Kurve")
        cl = QVBoxLayout(gb_curve)
        self.sensors_lbl = QLabel("Sensoren: —")
        self.sensors_lbl.setWordWrap(True)
        cl.addWidget(self.sensors_lbl)
        self.curve_table = QTableWidget(0, 2)
        self.curve_table.setHorizontalHeaderLabels(["Temperatur", "Level"])
        self.curve_table.verticalHeader().setVisible(False)
        self.curve_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.curve_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.curve_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        cl.addWidget(self.curve_table)
        root.addWidget(gb_curve)

        row = QHBoxLayout()
        self.refresh_btn = QPushButton("Aktualisieren")
        self.refresh_btn.clicked.connect(self.refresh)
        row.addStretch(1)
        row.addWidget(self.refresh_btn)
        root.addLayout(row)

        root.addStretch(1)

    def refresh(self) -> None:
        self._set_label(self.mode_lbl, self._get("Mode"))
        self._set_label(self.level_lbl, self._get("CurrentLevel"))
        fs = self._get("FailsafeTemp")
        self.failsafe_lbl.setText(f"{float(fs):.1f} °C" if fs is not None else "—")
        self._set_label(self.version_lbl, self._get("DaemonVersion"))

        sensors = self._get("CurveSensors") or []
        self.sensors_lbl.setText("Sensoren: " + (", ".join(sensors) if sensors else "—"))

        rows = _fmt_curve(self._get("Curve") or [])
        self.curve_table.setRowCount(len(rows))
        for i, (t, l) in enumerate(rows):
            it_t = QTableWidgetItem(t)
            it_l = QTableWidgetItem(l)
            it_t.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_l.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.curve_table.setItem(i, 0, it_t)
            self.curve_table.setItem(i, 1, it_l)

    def _get(self, name: str) -> Any:
        try:
            return self._client.get(name)
        except Exception:
            return None

    @staticmethod
    def _set_label(lbl: QLabel, value: Any) -> None:
        lbl.setText(str(value) if value not in (None, "") else "—")
