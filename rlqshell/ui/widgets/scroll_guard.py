"""Utility to prevent wheel events from accidentally changing form widget values."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QWidget


class _WheelGuard(QObject):
    """Event filter that ignores wheel events so the parent scroll area handles them."""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Wheel:
            event.ignore()
            return False
        return super().eventFilter(obj, event)


_guard = _WheelGuard()


def install_scroll_guard(*widgets: QWidget) -> None:
    """Install wheel-event guard on combo/spin boxes inside a QScrollArea form.

    Prevents accidental value changes when the user scrolls over these widgets
    without first clicking on them.
    """
    for w in widgets:
        w.installEventFilter(_guard)
        if isinstance(w, (QComboBox, QAbstractSpinBox)):
            w.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
