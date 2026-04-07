"""General settings — language, confirmations, startup behavior."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.config import ConfigManager
from rlqshell.app.constants import Colors
from rlqshell.ui.widgets.toggle_switch import ToggleSwitch


class GeneralSettings(QWidget):
    """General configuration panel."""

    def __init__(self, config: ConfigManager, parent=None) -> None:
        super().__init__(parent)
        self._config = config

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("General")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        layout.addWidget(title)

        # --- Confirmations section ---
        section_label = QLabel("Confirmation Dialogs")
        section_label.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent; margin-top: 8px;"
        )
        layout.addWidget(section_label)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Confirm on close app
        self._confirm_app = ToggleSwitch()
        self._confirm_app.set_checked(config.get("general.confirm_close_app", True))
        self._confirm_app.toggled.connect(
            lambda v: self._save("general.confirm_close_app", v)
        )
        form.addRow(self._make_label("Confirm on exit"), self._confirm_app)

        # Confirm on close tab
        self._confirm_tab = ToggleSwitch()
        self._confirm_tab.set_checked(config.get("general.confirm_close_tab", True))
        self._confirm_tab.toggled.connect(
            lambda v: self._save("general.confirm_close_tab", v)
        )
        form.addRow(self._make_label("Confirm on tab close"), self._confirm_tab)

        layout.addLayout(form)
        layout.addStretch()

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 13px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        return lbl

    def _save(self, key: str, value) -> None:
        self._config.set(key, value)
        self._config.save()
