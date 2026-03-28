"""Floating window for a detached connection tab."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from termplus.app.constants import APP_NAME, Colors


class DetachedTabWindow(QMainWindow):
    """Floating window holding a single detached session."""

    dock_requested = Signal(str)   # tab_id
    closed = Signal(str)           # tab_id

    def __init__(
        self,
        tab_id: str,
        label: str,
        protocol: str,
        color: str | None,
        content_widget: QWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tab_id = tab_id
        self._label = label
        self._protocol = protocol
        self._color = color
        self._closing_from_dock = False

        self.setWindowTitle(f"{APP_NAME} — {protocol.upper()} {label}")
        self.setMinimumSize(640, 480)
        self.resize(900, 600)

        # Central widget
        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Custom title bar
        title_bar = QWidget()
        title_bar.setFixedHeight(36)
        title_bar.setStyleSheet(f"background-color: {Colors.BG_DARKER};")

        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(12, 0, 8, 0)
        tb_layout.setSpacing(8)

        # Protocol badge
        proto_label = QLabel(protocol.upper())
        proto_label.setFixedSize(36, 18)
        proto_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        proto_label.setStyleSheet(
            f"font-size: 9px; font-weight: 700; color: {Colors.TEXT_MUTED}; "
            f"background-color: {Colors.BG_HOVER}; border-radius: 3px; "
            f"padding: 1px 4px;"
        )
        tb_layout.addWidget(proto_label)

        # Color dot
        if color:
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(
                f"background-color: {color}; border-radius: 4px;"
            )
            tb_layout.addWidget(dot)

        # Label
        name_label = QLabel(label)
        name_label.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        tb_layout.addWidget(name_label, 1)

        # Dock-back button
        dock_btn = QPushButton("Dock")
        dock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dock_btn.setToolTip("Dock back to main window")
        dock_btn.setStyleSheet(
            f"QPushButton {{ font-size: 11px; font-weight: 600; "
            f"color: {Colors.TEXT_PRIMARY}; background-color: {Colors.ACCENT}; "
            f"border: none; border-radius: 4px; padding: 3px 10px; }}"
            f"QPushButton:hover {{ background-color: {Colors.ACCENT_HOVER}; }}"
        )
        dock_btn.clicked.connect(lambda: self.dock_requested.emit(self._tab_id))
        tb_layout.addWidget(dock_btn)

        main_layout.addWidget(title_bar)

        # Session content (addWidget handles reparenting)
        main_layout.addWidget(content_widget, 1)

        self.setCentralWidget(central)
        self.setStyleSheet(f"QMainWindow {{ background-color: {Colors.BG_PRIMARY}; }}")

        # Position at cursor
        self.move(QCursor.pos())

    @property
    def tab_id(self) -> str:
        return self._tab_id

    @property
    def label_text(self) -> str:
        return self._label

    @property
    def protocol(self) -> str:
        return self._protocol

    @property
    def color(self) -> str | None:
        return self._color

    def dock_back(self) -> QWidget | None:
        """Remove and return the content widget for re-docking."""
        central = self.centralWidget()
        if central is None:
            return None
        layout = central.layout()
        if layout and layout.count() >= 2:
            item = layout.itemAt(1)
            if item and item.widget():
                widget = item.widget()
                layout.removeWidget(widget)
                widget.setParent(None)
                return widget
        return None

    def close_for_dock(self) -> None:
        """Close without emitting the closed signal (used when docking back)."""
        self._closing_from_dock = True
        self.close()

    def closeEvent(self, event) -> None:
        if not self._closing_from_dock:
            self.closed.emit(self._tab_id)
        event.accept()
