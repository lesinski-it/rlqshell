"""Sync status indicator — small icon in TopBar showing cloud sync state."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

from termplus.app.constants import Colors


class SyncStatusIndicator(QWidget):
    """Cloud sync status icon with tooltip."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(24, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._icon = QLabel("☁", self)
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon.setFixedSize(24, 24)
        self._set_status("idle")

    def _set_status(self, status: str) -> None:
        if status == "syncing":
            color = Colors.WARNING
            tooltip = "Syncing..."
        elif status == "error":
            color = Colors.DANGER
            tooltip = "Sync error"
        elif status == "connected":
            color = Colors.SUCCESS
            tooltip = "Sync connected"
        else:
            color = Colors.TEXT_MUTED
            tooltip = "Sync idle"

        self._icon.setStyleSheet(
            f"font-size: 14px; color: {color}; background: transparent;"
        )
        self.setToolTip(tooltip)

    def set_syncing(self) -> None:
        self._set_status("syncing")

    def set_error(self) -> None:
        self._set_status("error")

    def set_connected(self) -> None:
        self._set_status("connected")

    def set_idle(self) -> None:
        self._set_status("idle")
