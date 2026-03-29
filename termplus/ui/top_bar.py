"""Top navigation bar — Vault | Connections | SFTP | Port Forwarding."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from termplus.app.constants import Colors


class TopBar(QWidget):
    """Horizontal top navigation bar with page buttons and status area."""

    page_changed = Signal(int)
    settings_requested = Signal()

    # Page indices
    PAGE_VAULT = 0
    PAGE_CONNECTIONS = 1
    PAGE_SFTP = 2
    PAGE_PORT_FORWARD = 3

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setStyleSheet(f"background-color: {Colors.BG_DARKER};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(0)

        # Logo
        logo = QLabel("Termplus")
        logo.setStyleSheet(
            f"color: {Colors.ACCENT_LIGHT}; font-size: 16px; font-weight: 700; "
            f"background: transparent; padding-right: 24px;"
        )
        layout.addWidget(logo)

        # Navigation buttons
        self._nav_buttons: list[QPushButton] = []
        nav_items = [
            ("Vault", self.PAGE_VAULT),
            ("Connections", self.PAGE_CONNECTIONS),
            ("SFTP", self.PAGE_SFTP),
            ("Port Forwarding", self.PAGE_PORT_FORWARD),
        ]
        for label, index in nav_items:
            btn = self._create_nav_button(label, index)
            self._nav_buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

        # Track counts for inline display
        self._connection_count = 0
        self._sftp_count = 0

        layout.addSpacing(12)

        # Settings button
        settings_btn = QPushButton("Settings")
        settings_btn.setProperty("cssClass", "flat")
        settings_btn.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; background: transparent; "
            f"border: none; padding: 6px 12px; font-size: 12px;"
        )
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.clicked.connect(self.settings_requested.emit)
        layout.addWidget(settings_btn)

        # Set default selection
        self._current_index = 0
        self._update_button_styles()

    def _create_nav_button(self, label: str, index: int) -> QPushButton:
        btn = QPushButton(label)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(self._nav_button_style(False))
        btn.clicked.connect(lambda checked=False, i=index: self._on_nav_click(i))
        return btn

    def navigate_to(self, index: int) -> None:
        """Programmatically switch to the given page index."""
        self._current_index = index
        self._update_button_styles()
        self.page_changed.emit(index)

    def _on_nav_click(self, index: int) -> None:
        if index != self._current_index:
            self.navigate_to(index)

    def _update_button_styles(self) -> None:
        for i, btn in enumerate(self._nav_buttons):
            btn.setStyleSheet(self._nav_button_style(i == self._current_index))

    def set_connection_count(self, count: int) -> None:
        """Update the Connections button label with count."""
        self._connection_count = count
        btn = self._nav_buttons[self.PAGE_CONNECTIONS]
        btn.setText(f"Connections ({count})" if count > 0 else "Connections")

    def set_sftp_count(self, count: int) -> None:
        """Update the SFTP button label with count."""
        self._sftp_count = count
        btn = self._nav_buttons[self.PAGE_SFTP]
        btn.setText(f"SFTP ({count})" if count > 0 else "SFTP")

    @staticmethod
    def _nav_button_style(active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ "
                f"  background: transparent; border: none; "
                f"  color: {Colors.TEXT_PRIMARY}; font-weight: 600; "
                f"  padding: 12px 16px; font-size: 13px; "
                f"  border-bottom: 2px solid {Colors.ACCENT}; "
                f"}}"
            )
        return (
            f"QPushButton {{ "
            f"  background: transparent; border: none; "
            f"  color: {Colors.TEXT_SECONDARY}; font-weight: 500; "
            f"  padding: 12px 16px; font-size: 13px; "
            f"  border-bottom: 2px solid transparent; "
            f"}}"
            f"QPushButton:hover {{ "
            f"  color: {Colors.TEXT_PRIMARY}; "
            f"  background-color: {Colors.BG_SURFACE}; "
            f"}}"
        )
