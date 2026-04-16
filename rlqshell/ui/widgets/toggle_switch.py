"""iOS-style toggle switch widget."""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from rlqshell.app.constants import Colors


class ToggleSwitch(QWidget):
    """Animated toggle switch with checked/unchecked states."""

    toggled = Signal(bool)

    def __init__(
        self,
        checked: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFixedSize(44, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._checked = checked
        self._thumb_position = 20.0 if checked else 4.0

        self._animation = QPropertyAnimation(self, b"thumb_position")
        self._animation.setDuration(200)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

    @Property(float)
    def thumb_position(self) -> float:
        return self._thumb_position

    @thumb_position.setter  # type: ignore[no-redef]
    def thumb_position(self, value: float) -> None:
        self._thumb_position = value
        self.update()

    def is_checked(self) -> bool:
        return self._checked

    def set_checked(self, checked: bool, animate: bool = True) -> None:
        """Set the switch state."""
        if checked == self._checked:
            return
        self._checked = checked
        target = 20.0 if checked else 4.0
        if animate:
            self._animation.stop()
            self._animation.setStartValue(self._thumb_position)
            self._animation.setEndValue(target)
            self._animation.start()
        else:
            self._thumb_position = target
            self.update()
        self.toggled.emit(checked)

    def mousePressEvent(self, event) -> None:
        self.set_checked(not self._checked)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Track
        track_color = QColor(Colors.ACCENT if self._checked else Colors.BG_HOVER)
        painter.setBrush(track_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(0, 0, 44, 24), 12, 12)

        # Thumb
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(self._thumb_position, 4, 16, 16))

        painter.end()
