"""Icon-only button with hover effect and tooltip."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QPushButton, QWidget

from termplus.app.constants import Colors


class IconButton(QPushButton):
    """Borderless icon button with circular hover background."""

    def __init__(
        self,
        icon: QIcon | str | None = None,
        tooltip: str = "",
        size: int = 32,
        icon_size: int = 18,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFixedSize(QSize(size, size))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)

        if isinstance(icon, str):
            self.setIcon(QIcon(icon))
        elif isinstance(icon, QIcon):
            self.setIcon(icon)

        self.setIconSize(QSize(icon_size, icon_size))

        radius = size // 2
        self.setStyleSheet(
            f"QPushButton {{ "
            f"  background: transparent; border: none; border-radius: {radius}px; "
            f"  color: {Colors.TEXT_SECONDARY}; "
            f"}}"
            f"QPushButton:hover {{ background-color: {Colors.BG_SURFACE}; }}"
            f"QPushButton:pressed {{ background-color: {Colors.BG_HOVER}; }}"
        )
