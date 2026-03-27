"""Settings dialog — sidebar categories + settings panels."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QVBoxLayout,
)

from termplus.app.config import ConfigManager
from termplus.app.constants import Colors
from termplus.ui.settings.appearance_settings import AppearanceSettings
from termplus.ui.settings.keybinding_settings import KeybindingSettings
from termplus.ui.settings.sync_settings import SyncSettings
from termplus.ui.settings.terminal_settings import TerminalSettings

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """Modal settings dialog with sidebar navigation."""

    def __init__(self, config: ConfigManager, parent=None, sync_engine=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setFixedSize(700, 500)
        self._sync_engine = sync_engine

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sidebar
        self._sidebar = QListWidget()
        self._sidebar.setFixedWidth(180)
        self._sidebar.setStyleSheet(
            f"QListWidget {{ "
            f"  background-color: {Colors.BG_DARKER}; border: none; "
            f"  border-right: 1px solid {Colors.BORDER}; outline: none; "
            f"}}"
            f"QListWidget::item {{ "
            f"  padding: 10px 16px; color: {Colors.TEXT_SECONDARY}; "
            f"  font-size: 13px; "
            f"}}"
            f"QListWidget::item:selected {{ "
            f"  background-color: {Colors.BG_SURFACE}; "
            f"  color: {Colors.TEXT_PRIMARY}; font-weight: 600; "
            f"  border-left: 3px solid {Colors.ACCENT}; "
            f"}}"
            f"QListWidget::item:hover {{ "
            f"  background-color: {Colors.BG_SURFACE}; "
            f"}}"
        )
        layout.addWidget(self._sidebar)

        # Content stack
        self._stack = QStackedWidget()
        self._stack.setStyleSheet(
            f"QStackedWidget {{ background-color: {Colors.BG_PRIMARY}; }}"
        )
        layout.addWidget(self._stack, 1)

        # Add settings pages
        self._add_page("Terminal", TerminalSettings(config))
        self._add_page("Appearance", AppearanceSettings(config))
        self._add_page("Key Bindings", KeybindingSettings(config))
        self._add_page("Sync", SyncSettings(config, sync_engine=sync_engine))

        self._sidebar.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._sidebar.setCurrentRow(0)

    def _add_page(self, name: str, widget) -> None:
        item = QListWidgetItem(name)
        self._sidebar.addItem(item)
        self._stack.addWidget(widget)
