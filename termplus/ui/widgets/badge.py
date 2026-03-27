"""Status badge — colored circle indicator."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from termplus.app.constants import Colors

STATUS_COLORS = {
    "connected": Colors.CONNECTED,
    "disconnected": Colors.DISCONNECTED,
    "connecting": Colors.CONNECTING,
    "error": Colors.ERROR,
}


class StatusBadge(QWidget):
    """A small colored circle indicating status."""

    def __init__(
        self,
        status: str = "disconnected",
        size: int = 10,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._status = status
        self._size = size
        self.setFixedSize(QSize(size, size))

    @property
    def status(self) -> str:
        return self._status

    @status.setter
    def status(self, value: str) -> None:
        self._status = value
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(STATUS_COLORS.get(self._status, Colors.DISCONNECTED))
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, self._size, self._size)
        painter.end()
