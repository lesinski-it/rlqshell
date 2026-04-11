"""Update settings — auto-check toggle, interval, manual check button."""

from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.config import ConfigManager
from rlqshell.app.constants import APP_VERSION, Colors
from rlqshell.ui.widgets.toggle_switch import ToggleSwitch

logger = logging.getLogger(__name__)


class UpdateSettings(QWidget):
    """Settings page for application updates."""

    def __init__(
        self,
        config: ConfigManager,
        update_manager=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._updater = update_manager

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Updates")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        layout.addWidget(title)

        desc = QLabel(
            "Automatically check for new versions. "
            "Updates are downloaded and verified before installation."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        layout.addWidget(desc)

        # form
        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._auto_check = ToggleSwitch()
        self._auto_check.set_checked(config.get("updates.auto_check", True))
        self._auto_check.toggled.connect(self._on_auto_check_toggled)
        form.addRow(self._make_label("Automatic checking"), self._auto_check)

        self._interval = QSpinBox()
        self._interval.setRange(1, 168)
        self._interval.setSuffix(" h")
        self._interval.setValue(config.get("updates.check_interval_hours", 24))
        self._interval.setStyleSheet(
            f"QSpinBox {{ "
            f"  background-color: {Colors.BG_SURFACE}; color: {Colors.TEXT_PRIMARY}; "
            f"  border: 1px solid {Colors.BORDER}; border-radius: 4px; "
            f"  padding: 4px 8px; font-size: 13px; "
            f"}}"
        )
        self._interval.valueChanged.connect(self._on_interval_changed)
        form.addRow(self._make_label("Check interval"), self._interval)

        layout.addLayout(form)

        # current version
        ver_label = QLabel(f"Current version: v{APP_VERSION}")
        ver_label.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_MUTED}; "
            f"background: transparent; margin-top: 8px;"
        )
        layout.addWidget(ver_label)

        # check now row
        check_row = QHBoxLayout()

        self._check_btn = QPushButton("Check now")
        self._check_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._check_btn.setStyleSheet(
            f"QPushButton {{ "
            f"  background-color: {Colors.ACCENT}; color: #ffffff; "
            f"  border: none; border-radius: 6px; "
            f"  padding: 8px 16px; font-size: 13px; font-weight: 600; "
            f"}}"
            f"QPushButton:hover {{ background-color: {Colors.ACCENT_HOVER}; }}"
        )
        self._check_btn.clicked.connect(self._on_check_now)
        check_row.addWidget(self._check_btn)
        check_row.addStretch()

        layout.addLayout(check_row)

        # status
        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_MUTED}; background: transparent;"
        )
        layout.addWidget(self._status)

        layout.addStretch()

        # connect updater signals
        if self._updater:
            self._updater.update_available.connect(self._on_update_found)
            self._updater.check_failed.connect(self._on_check_failed)

    # -- slots --

    def _on_auto_check_toggled(self, checked: bool) -> None:
        self._config.set("updates.auto_check", checked)
        self._config.save()
        if self._updater:
            self._updater.stop()
            if checked:
                self._updater.start()

    def _on_interval_changed(self, value: int) -> None:
        self._config.set("updates.check_interval_hours", value)
        self._config.save()
        if self._updater and self._config.get("updates.auto_check", True):
            self._updater.stop()
            self._updater.start()

    def _on_check_now(self) -> None:
        if not self._updater:
            return
        self._check_btn.setEnabled(False)
        self._check_btn.setText("Checking…")
        self._status.setText("")
        self._status.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_MUTED}; background: transparent;"
        )

        async def _do_check() -> None:
            result = await self._updater.check_for_update()
            self._check_btn.setEnabled(True)
            self._check_btn.setText("Check now")
            if result is None and not self._updater._checking:
                self._status.setText("You are running the latest version.")
                self._status.setStyleSheet(
                    f"font-size: 12px; color: {Colors.SUCCESS}; background: transparent;"
                )

        asyncio.ensure_future(_do_check())

    def _on_update_found(self, manifest: dict) -> None:
        version = manifest.get("version", "?")
        self._status.setText(f"Update available: v{version}")
        self._status.setStyleSheet(
            f"font-size: 12px; color: {Colors.ACCENT}; font-weight: 600; "
            f"background: transparent;"
        )
        self._check_btn.setEnabled(True)
        self._check_btn.setText("Check now")

    def _on_check_failed(self, error: str) -> None:
        self._status.setText(f"Error: {error}")
        self._status.setStyleSheet(
            f"font-size: 12px; color: {Colors.DANGER}; background: transparent;"
        )
        self._check_btn.setEnabled(True)
        self._check_btn.setText("Check now")

    # -- helpers --

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 13px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        return lbl
