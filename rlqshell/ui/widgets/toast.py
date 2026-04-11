"""Toast notification system."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QTimer, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from rlqshell.app.constants import Colors

_TOAST_COLORS = {
    "info": Colors.INFO,
    "success": Colors.SUCCESS,
    "warning": Colors.WARNING,
    "error": Colors.DANGER,
}


class ToastNotification(QWidget):
    """Small auto-dismissing notification at the bottom of the window."""

    clicked = Signal()

    def __init__(
        self,
        message: str,
        toast_type: str = "info",
        duration_ms: int = 3000,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        color = _TOAST_COLORS.get(toast_type, Colors.INFO)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        container = QWidget()
        container.setStyleSheet(
            f"background-color: {Colors.BG_SURFACE}; "
            f"border: 1px solid {color}; "
            f"border-radius: 8px; "
            f"border-left: 4px solid {color};"
        )
        inner = QHBoxLayout(container)
        inner.setContentsMargins(16, 12, 16, 12)

        label = QLabel(message)
        label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px; background: transparent;")
        inner.addWidget(label)

        layout.addWidget(container)
        self.adjustSize()

        # Auto dismiss
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._dismiss)
        self._timer.start(duration_ms)

    def show_at_bottom(self, parent: QWidget) -> None:
        """Position at the bottom center of the parent widget."""
        parent_rect = parent.rect()
        x = parent.mapToGlobal(parent_rect.center()).x() - self.width() // 2
        y = parent.mapToGlobal(parent_rect.bottomLeft()).y() - self.height() - 20
        self.move(x, y)
        self.show()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.clicked.emit()
        self._dismiss()

    def _dismiss(self) -> None:
        self.close()
        self.deleteLater()


class ToastManager:
    """Singleton manager for toast notifications."""

    _instance: ToastManager | None = None

    def __init__(self) -> None:
        self._parent: QWidget | None = None

    @classmethod
    def instance(cls) -> ToastManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_parent(self, parent: QWidget) -> None:
        self._parent = parent

    def show_toast(
        self,
        message: str,
        toast_type: str = "info",
        duration_ms: int = 3000,
        on_click: Callable[[], None] | None = None,
    ) -> None:
        """Show a toast notification."""
        if self._parent is None:
            return
        toast = ToastNotification(message, toast_type, duration_ms, self._parent)
        if on_click is not None:
            toast.clicked.connect(on_click)
            toast.setCursor(Qt.CursorShape.PointingHandCursor)
        toast.show_at_bottom(self._parent)
