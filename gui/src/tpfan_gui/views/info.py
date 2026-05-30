"""Info view with authorship, license and contact details."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .. import __version__ as GUI_VERSION


class InfoView(QWidget):
    """Displays project authorship, license and contact information."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for text in (
            f"Version: {GUI_VERSION}",
            "made by Matthias Gruß with Claude Code by Anthropic",
            "Lizenz: GPLv3 oder neuer",
            "Kontakt: matthiasgruss@posteo.de",
        ):
            label = QLabel(text)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            layout.addWidget(label)
