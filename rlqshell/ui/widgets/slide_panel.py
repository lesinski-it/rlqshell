"""Animated slide-in panel from the right side."""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from rlqshell.app.constants import Colors


class SlidePanel(QFrame):
    """A panel that slides in from the right side of its parent.

    Usage:
        panel = SlidePanel(parent=self, width=400)
        panel.set_content(some_widget)
        panel.open()
    """

    def __init__(
        self,
        parent: QWidget,
        width: int = 400,
    ) -> None:
        super().__init__(parent)
        self._panel_width = width
        self._is_open = False

        self.setFixedWidth(0)
        self.hide()
        self.setStyleSheet(
            f"SlidePanel {{ "
            f"  background-color: {Colors.BG_SURFACE}; "
            f"  border-left: 1px solid {Colors.BORDER}; "
            f"}}"
        )

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        # Width animation — uses the registered panelWidth Property
        self._animation = QPropertyAnimation(self, b"panelWidth")
        self._animation.setDuration(250)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    # --- Qt Property for animation ---

    def _get_panel_width(self) -> int:
        return self.maximumWidth()

    def _set_panel_width(self, width: int) -> None:
        self.setFixedWidth(max(0, width))

    panelWidth = Property(int, _get_panel_width, _set_panel_width)

    # --- Public API ---

    @property
    def is_open(self) -> bool:
        return self._is_open

    def set_content(self, widget: QWidget) -> None:
        """Set the panel content widget."""
        # Clear existing
        while self._layout.count() > 0:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._layout.addWidget(widget)

    def open(self) -> None:
        """Slide the panel open."""
        if self._is_open:
            return
        self._is_open = True
        self.show()
        self._animation.stop()
        self._animation.setStartValue(self.maximumWidth())
        self._animation.setEndValue(self._panel_width)
        self._animation.start()

    def close(self) -> None:
        """Slide the panel closed."""
        if not self._is_open:
            return
        self._is_open = False
        self._animation.stop()
        self._animation.setStartValue(self.maximumWidth())
        self._animation.setEndValue(0)
        self._animation.finished.connect(self._on_close_finished)
        self._animation.start()

    def toggle(self) -> None:
        """Toggle the panel open/closed."""
        if self._is_open:
            self.close()
        else:
            self.open()

    def _on_close_finished(self) -> None:
        self._animation.finished.disconnect(self._on_close_finished)
        self.hide()
