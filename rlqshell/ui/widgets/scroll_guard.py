"""Utility to prevent wheel events from accidentally changing form widget values."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QComboBox, QWidget


class _WheelGuard(QObject):
    """Event filter that blocks wheel events on combo/spin boxes.

    Returns True to prevent the widget from changing its value, then forwards
    the event to the parent so the enclosing QScrollArea can scroll normally.
    """

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Wheel:
            parent = obj.parentWidget()
            if parent is not None:
                QApplication.sendEvent(parent, event)
            return True  # block widget from handling it
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
