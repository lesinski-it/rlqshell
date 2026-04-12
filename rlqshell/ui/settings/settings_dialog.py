"""Settings dialog — sidebar categories + settings panels."""

from __future__ import annotations

import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
)

from rlqshell.app.config import ConfigManager
from rlqshell.app.constants import Colors
from rlqshell.ui.settings.about_settings import AboutSettings
from rlqshell.ui.settings.appearance_settings import AppearanceSettings
from rlqshell.ui.settings.general_settings import GeneralSettings
from rlqshell.ui.settings.keybinding_settings import KeybindingSettings
from rlqshell.ui.settings.sync_settings import SyncSettings
from rlqshell.ui.settings.terminal_settings import TerminalSettings
from rlqshell.ui.settings.update_settings import UpdateSettings

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """Modal settings dialog with sidebar navigation."""

    terminal_settings_changed = Signal()
    appearance_settings_changed = Signal()

    def __init__(
        self,
        config: ConfigManager,
        parent=None,
        sync_engine=None,
        update_manager=None,
        token_store=None,
        credential_store=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setFixedSize(700, 500)
        self._sync_engine = sync_engine
        self._update_manager = update_manager
        self._token_store = token_store
        self._credential_store = credential_store

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
        self._add_page("General", GeneralSettings(config))
        terminal_page = TerminalSettings(config)
        terminal_page.terminal_settings_changed.connect(self.terminal_settings_changed)
        self._add_page("Terminal", terminal_page)
        appearance_page = AppearanceSettings(config)
        appearance_page.appearance_settings_changed.connect(self.appearance_settings_changed)
        self._add_page("Appearance", appearance_page)
        self._add_page("Key Bindings", KeybindingSettings(config))
        self._add_page("Sync", SyncSettings(
            config, sync_engine=sync_engine,
            token_store=token_store, credential_store=credential_store,
        ))
        self._add_page("Updates", UpdateSettings(config, update_manager=update_manager))
        self._add_page("About", AboutSettings())

        self._sidebar.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._sidebar.setCurrentRow(0)

    def _add_page(self, name: str, widget) -> None:
        item = QListWidgetItem(name)
        self._sidebar.addItem(item)
        self._stack.addWidget(widget)
