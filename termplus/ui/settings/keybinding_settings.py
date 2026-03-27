"""Key binding settings — action-shortcut mapping."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from termplus.app.config import ConfigManager
from termplus.app.constants import Colors

# Default keybindings
_DEFAULTS = {
    "Command Palette": "Ctrl+K",
    "Settings": "Ctrl+,",
    "New Host": "Ctrl+N",
    "Close Tab": "Ctrl+W",
    "Next Tab": "Ctrl+Tab",
    "Previous Tab": "Ctrl+Shift+Tab",
    "Copy": "Ctrl+Shift+C",
    "Paste": "Ctrl+Shift+V",
    "Find": "Ctrl+Shift+F",
    "Toggle Fullscreen": "F11",
}


class KeybindingSettings(QWidget):
    """Key binding configuration panel."""

    def __init__(self, config: ConfigManager, parent=None) -> None:
        super().__init__(parent)
        self._config = config

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Key Bindings")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        header.addWidget(title)
        header.addStretch()

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.clicked.connect(self._reset_defaults)
        header.addWidget(reset_btn)

        layout.addLayout(header)

        # Keybinding table
        self._table = QTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(["Action", "Shortcut"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        self._load_bindings()

    def _load_bindings(self) -> None:
        bindings = self._config.get("keybindings", {})
        if not isinstance(bindings, dict):
            bindings = {}

        # Merge with defaults
        merged = dict(_DEFAULTS)
        merged.update(bindings)

        self._table.setRowCount(len(merged))
        for row, (action, shortcut) in enumerate(merged.items()):
            self._table.setItem(row, 0, QTableWidgetItem(action))

            shortcut_item = QTableWidgetItem(shortcut)
            shortcut_item.setForeground(
                QLabel().palette().text().color()
            )
            self._table.setItem(row, 1, shortcut_item)

    def _reset_defaults(self) -> None:
        self._config.set("keybindings", {})
        self._config.save()
        self._load_bindings()
