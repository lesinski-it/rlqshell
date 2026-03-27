"""Sync settings — provider selection, connect/disconnect, status."""

from __future__ import annotations

import asyncio
import logging
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from termplus.app.config import ConfigManager
from termplus.app.constants import Colors
from termplus.ui.widgets.toggle_switch import ToggleSwitch

logger = logging.getLogger(__name__)


class SyncSettings(QWidget):
    """Sync configuration panel inside Settings dialog."""

    def __init__(
        self,
        config: ConfigManager,
        sync_engine=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._sync_engine = sync_engine

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Cloud Sync")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        layout.addWidget(title)

        desc = QLabel(
            "Sync your hosts, keys, and settings across devices via cloud storage. "
            "Data is encrypted before upload."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        layout.addWidget(desc)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Provider selection
        self._provider_combo = QComboBox()
        self._provider_combo.addItems(["None", "OneDrive", "Google Drive", "Dropbox"])
        current = config.get("sync.provider", "None")
        self._provider_combo.setCurrentText(current)
        self._provider_combo.currentTextChanged.connect(self._on_provider_changed)
        form.addRow(self._make_label("Provider"), self._provider_combo)

        # Auto-sync toggle
        self._auto_sync = ToggleSwitch()
        self._auto_sync.setChecked(config.get("sync.auto_sync", False))
        self._auto_sync.toggled.connect(lambda v: self._save("sync.auto_sync", v))
        form.addRow(self._make_label("Auto Sync"), self._auto_sync)

        # Sync interval
        self._interval = QSpinBox()
        self._interval.setRange(1, 60)
        self._interval.setSuffix(" min")
        self._interval.setValue(config.get("sync.interval_minutes", 5))
        self._interval.valueChanged.connect(
            lambda v: self._save("sync.interval_minutes", v)
        )
        form.addRow(self._make_label("Sync Interval"), self._interval)

        layout.addLayout(form)

        # Status area
        status_layout = QHBoxLayout()

        self._status_label = QLabel("Not connected")
        self._status_label.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_MUTED}; background: transparent;"
        )
        status_layout.addWidget(self._status_label)
        status_layout.addStretch()

        self._last_sync_label = QLabel("")
        self._last_sync_label.setStyleSheet(
            f"font-size: 11px; color: {Colors.TEXT_MUTED}; background: transparent;"
        )
        status_layout.addWidget(self._last_sync_label)

        layout.addLayout(status_layout)

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setProperty("cssClass", "primary")
        self._connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._connect_btn.clicked.connect(self._on_connect)
        btn_layout.addWidget(self._connect_btn)

        self._sync_now_btn = QPushButton("Sync Now")
        self._sync_now_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sync_now_btn.setEnabled(False)
        self._sync_now_btn.clicked.connect(self._on_sync_now)
        btn_layout.addWidget(self._sync_now_btn)

        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setProperty("cssClass", "danger")
        self._disconnect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._disconnect_btn.setEnabled(False)
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        btn_layout.addWidget(self._disconnect_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch()

        self._update_status()

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 13px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        return lbl

    def _save(self, key: str, value) -> None:
        self._config.set(key, value)
        self._config.save()

    def _on_provider_changed(self, provider: str) -> None:
        self._save("sync.provider", provider)
        self._update_status()

    def _on_connect(self) -> None:
        if not self._sync_engine:
            return

        provider_name = self._provider_combo.currentText()
        if provider_name == "None":
            return

        provider = self._sync_engine.provider
        if provider is None:
            logger.warning("No provider configured in sync engine")
            return

        # Open browser for OAuth
        auth_url = provider.get_auth_url()
        webbrowser.open(auth_url)
        self._status_label.setText("Waiting for authorization...")
        logger.info("Opened browser for %s OAuth", provider_name)

    def _on_sync_now(self) -> None:
        if self._sync_engine:
            asyncio.ensure_future(self._sync_engine.sync())

    def _on_disconnect(self) -> None:
        if self._sync_engine and self._sync_engine.provider:
            asyncio.ensure_future(self._sync_engine.provider.disconnect())
            self._sync_engine.stop_auto_sync()
            self._save("sync.provider", "None")
            self._provider_combo.setCurrentText("None")
            self._update_status()

    def _update_status(self) -> None:
        provider = self._provider_combo.currentText()
        connected = (
            self._sync_engine is not None
            and self._sync_engine.provider is not None
            and self._sync_engine.provider.is_authenticated()
        )

        if provider == "None":
            self._status_label.setText("Sync disabled")
            self._connect_btn.setEnabled(False)
            self._sync_now_btn.setEnabled(False)
            self._disconnect_btn.setEnabled(False)
        elif connected:
            self._status_label.setText(f"Connected to {provider}")
            self._status_label.setStyleSheet(
                f"font-size: 12px; color: {Colors.SUCCESS}; background: transparent;"
            )
            self._connect_btn.setEnabled(False)
            self._sync_now_btn.setEnabled(True)
            self._disconnect_btn.setEnabled(True)
        else:
            self._status_label.setText(f"Not connected to {provider}")
            self._status_label.setStyleSheet(
                f"font-size: 12px; color: {Colors.TEXT_MUTED}; background: transparent;"
            )
            self._connect_btn.setEnabled(True)
            self._sync_now_btn.setEnabled(False)
            self._disconnect_btn.setEnabled(False)
