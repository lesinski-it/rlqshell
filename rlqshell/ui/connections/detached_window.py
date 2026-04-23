"""Floating window for a detached connection tab."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import APP_NAME, Colors


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
        status_bar: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tab_id = tab_id
        self._label = label
        self._protocol = protocol
        self._color = color
        self._closing_from_dock = False
        self._status_bar = status_bar

        self.setWindowTitle(f"{APP_NAME} — {protocol.upper()} {label}")
        self.setMinimumSize(640, 480)
        self.resize(900, 600)

        # Central widget
        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Custom title bar
        self._title_bar = title_bar = QWidget()
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

        # Fullscreen toggle button
        fs_btn = QPushButton("⛶")
        fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fs_btn.setToolTip("Toggle fullscreen (F11)")
        fs_btn.setStyleSheet(
            f"QPushButton {{ font-size: 14px; font-weight: 600; "
            f"color: {Colors.TEXT_PRIMARY}; background-color: {Colors.BG_HOVER}; "
            f"border: none; border-radius: 4px; padding: 1px 8px; }}"
            f"QPushButton:hover {{ background-color: {Colors.BORDER}; }}"
        )
        fs_btn.clicked.connect(self.toggle_fullscreen)
        tb_layout.addWidget(fs_btn)

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

        # Wrap content in a container so layout fully manages it
        self._content_container = QWidget()
        container_layout = QVBoxLayout(self._content_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        container_layout.addWidget(content_widget)
        content_widget.setVisible(True)  # ensure visible after setParent(None)
        main_layout.addWidget(self._content_container, 1)

        # Optional status bar at the bottom (e.g. SSH server stats).
        # addWidget reparents the widget to the layout's owner (central), so
        # an explicit setParent() call here would be redundant and racy.
        if status_bar is not None:
            main_layout.addWidget(status_bar)
            status_bar.setVisible(True)

        self.setCentralWidget(central)
        self.setStyleSheet(f"QMainWindow {{ background-color: {Colors.BG_PRIMARY}; }}")

        # Position at cursor
        self.move(QCursor.pos())

        # F11 fullscreen scoped to this window only
        self._fs_shortcut = QShortcut(QKeySequence("F11"), self)
        self._fs_shortcut.activated.connect(self.toggle_fullscreen)

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
        container = self._content_container
        if container is None:
            return None
        layout = container.layout()
        if layout and layout.count() >= 1:
            item = layout.itemAt(0)
            if item and item.widget():
                widget = item.widget()
                layout.removeWidget(widget)
                widget.setParent(None)
                return widget
        return None

    def status_bar(self) -> QWidget | None:
        """Return the embedded status bar (if any)."""
        return self._status_bar

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            self._title_bar.setVisible(True)
            if self._status_bar is not None:
                self._status_bar.setVisible(True)
        else:
            self._title_bar.setVisible(False)
            if self._status_bar is not None:
                self._status_bar.setVisible(False)
            self.showFullScreen()

    def close_for_dock(self) -> None:
        """Close without emitting the closed signal (used when docking back)."""
        self._closing_from_dock = True
        self.close()

    def closeEvent(self, event) -> None:
        if self.isFullScreen():
            self.showNormal()
            self._title_bar.setVisible(True)
            if self._status_bar is not None:
                self._status_bar.setVisible(True)
        if not self._closing_from_dock:
            self.closed.emit(self._tab_id)
        event.accept()
