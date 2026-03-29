"""Vault sidebar with section navigation."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from termplus.app.constants import Colors

SECTIONS = [
    ("Hosts", "hosts"),
    ("Snippets", "snippets"),
    ("Keychain", "keychain"),
    ("Identities", "identities"),
    ("Known Hosts", "known_hosts"),
    ("Port Forwarding", "port_forward"),
    ("History", "history"),
]


class _SidebarItem(QPushButton):
    """Single sidebar navigation item."""

    def __init__(self, label: str, section_key: str, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.section_key = section_key
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.setFixedHeight(36)
        self._update_style(False)

    def _update_style(self, active: bool) -> None:
        if active:
            self.setStyleSheet(
                f"QPushButton {{ "
                f"  background-color: {Colors.BG_SURFACE}; "
                f"  border: none; border-left: 3px solid {Colors.ACCENT}; "
                f"  border-radius: 0; "
                f"  color: {Colors.TEXT_PRIMARY}; font-weight: 600; "
                f"  text-align: left; padding: 0 16px; font-size: 13px; "
                f"}}"
            )
        else:
            self.setStyleSheet(
                f"QPushButton {{ "
                f"  background: transparent; border: none; "
                f"  border-left: 3px solid transparent; border-radius: 0; "
                f"  color: {Colors.TEXT_SECONDARY}; font-weight: 500; "
                f"  text-align: left; padding: 0 16px; font-size: 13px; "
                f"}}"
                f"QPushButton:hover {{ "
                f"  background-color: {Colors.BG_SURFACE}; "
                f"  color: {Colors.TEXT_PRIMARY}; "
                f"}}"
            )

    def set_active(self, active: bool) -> None:
        self.setChecked(active)
        self._update_style(active)


class Sidebar(QWidget):
    """Left sidebar with section navigation items."""

    section_changed = Signal(str)  # section key

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(200)
        self.setStyleSheet(
            f"Sidebar {{ "
            f"  background-color: {Colors.BG_DARKER}; "
            f"  border-right: 1px solid {Colors.BORDER}; "
            f"}}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 12)
        layout.setSpacing(2)

        # Section header
        header = QLabel("VAULT")
        header.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 11px; font-weight: 700; "
            f"padding: 8px 20px; background: transparent; letter-spacing: 1px;"
        )
        layout.addWidget(header)

        # Section items
        self._items: list[_SidebarItem] = []
        for label, key in SECTIONS:
            item = _SidebarItem(label, key)
            item.clicked.connect(lambda checked=False, k=key: self._on_item_click(k))
            self._items.append(item)
            layout.addWidget(item)

        layout.addStretch()

        # Select first item
        if self._items:
            self._items[0].set_active(True)

    def _on_item_click(self, section_key: str) -> None:
        for item in self._items:
            item.set_active(item.section_key == section_key)
        self.section_changed.emit(section_key)

    def select_section(self, section_key: str) -> None:
        """Programmatically select a section."""
        if any(item.section_key == section_key for item in self._items):
            self._on_item_click(section_key)
