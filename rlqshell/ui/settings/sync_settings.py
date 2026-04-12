"""Sync settings — provider selection, connect/disconnect, status, proxy."""

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
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.config import ConfigManager
from rlqshell.app.constants import Colors
from rlqshell.ui.widgets.toggle_switch import ToggleSwitch

logger = logging.getLogger(__name__)


class SyncSettings(QWidget):
    """Sync configuration panel inside Settings dialog."""

    def __init__(
        self,
        config: ConfigManager,
        sync_engine=None,
        token_store=None,
        credential_store=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._sync_engine = sync_engine
        self._token_store = token_store
        self._credential_store = credential_store

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

        # Cloud folder
        self._cloud_folder = QLineEdit()
        self._cloud_folder.setText(config.get("sync.cloud_folder", "/RLQShell"))
        self._cloud_folder.setPlaceholderText("/RLQShell")
        self._cloud_folder.editingFinished.connect(self._on_cloud_folder_changed)
        form.addRow(self._make_label("Cloud Folder"), self._cloud_folder)

        folder_hint = QLabel("Folder will be created if it doesn't exist.")
        folder_hint.setStyleSheet(
            f"font-size: 11px; color: {Colors.TEXT_MUTED}; background: transparent;"
        )
        form.addRow("", folder_hint)

        # Auto-sync toggle
        self._auto_sync = ToggleSwitch()
        self._auto_sync.set_checked(config.get("sync.auto_sync", False))
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

        # Sync on startup
        self._sync_on_start = ToggleSwitch()
        self._sync_on_start.set_checked(config.get("sync.sync_on_start", False))
        self._sync_on_start.toggled.connect(
            lambda v: self._save("sync.sync_on_start", v)
        )
        form.addRow(self._make_label("Sync on Startup"), self._sync_on_start)

        # Sync on close
        self._sync_on_close = ToggleSwitch()
        self._sync_on_close.set_checked(config.get("sync.sync_on_close", False))
        self._sync_on_close.toggled.connect(
            lambda v: self._save("sync.sync_on_close", v)
        )
        form.addRow(self._make_label("Sync on Close"), self._sync_on_close)

        # Conflict strategy
        self._conflict_combo = QComboBox()
        self._conflict_combo.addItems(
            ["Last Write Wins", "Keep Local", "Keep Remote"]
        )
        strategy = config.get("sync.conflict_strategy", "last_write_wins")
        strategy_map = {
            "last_write_wins": "Last Write Wins",
            "keep_local": "Keep Local",
            "keep_remote": "Keep Remote",
        }
        self._conflict_combo.setCurrentText(
            strategy_map.get(strategy, "Last Write Wins")
        )
        self._conflict_combo.currentTextChanged.connect(self._on_conflict_changed)
        form.addRow(self._make_label("Conflict Strategy"), self._conflict_combo)

        layout.addLayout(form)

        # --- Proxy section ---
        proxy_title = QLabel("Proxy")
        proxy_title.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent; margin-top: 8px;"
        )
        layout.addWidget(proxy_title)

        proxy_form = QFormLayout()
        proxy_form.setSpacing(12)
        proxy_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._proxy_toggle = ToggleSwitch()
        self._proxy_toggle.set_checked(config.get("sync.proxy_enabled", False))
        self._proxy_toggle.toggled.connect(self._on_proxy_toggled)
        proxy_form.addRow(self._make_label("Use Proxy"), self._proxy_toggle)

        self._proxy_url = QLineEdit()
        self._proxy_url.setText(config.get("sync.proxy_url", ""))
        self._proxy_url.setPlaceholderText("http://proxy.corp.com:8080")
        self._proxy_url.setEnabled(config.get("sync.proxy_enabled", False))
        self._proxy_url.editingFinished.connect(
            lambda: self._save("sync.proxy_url", self._proxy_url.text().strip())
        )
        proxy_form.addRow(self._make_label("Proxy URL"), self._proxy_url)

        layout.addLayout(proxy_form)

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

    # --- Helpers ---

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 13px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        return lbl

    def _save(self, key: str, value) -> None:
        self._config.set(key, value)
        self._config.save()

    def _get_proxy_url(self) -> str | None:
        if self._config.get("sync.proxy_enabled", False):
            url = self._config.get("sync.proxy_url", "").strip()
            return url if url else None
        return None

    # --- Callbacks ---

    def _on_provider_changed(self, provider: str) -> None:
        self._save("sync.provider", provider)
        self._update_status()

    def _on_cloud_folder_changed(self) -> None:
        folder = self._cloud_folder.text().strip()
        if not folder.startswith("/"):
            folder = "/" + folder
            self._cloud_folder.setText(folder)
        self._save("sync.cloud_folder", folder)
        if self._sync_engine:
            self._sync_engine.cloud_folder = folder

    def _on_conflict_changed(self, text: str) -> None:
        reverse_map = {
            "Last Write Wins": "last_write_wins",
            "Keep Local": "keep_local",
            "Keep Remote": "keep_remote",
        }
        self._save("sync.conflict_strategy", reverse_map.get(text, "last_write_wins"))

    def _on_proxy_toggled(self, enabled: bool) -> None:
        self._save("sync.proxy_enabled", enabled)
        self._proxy_url.setEnabled(enabled)

    def _on_connect(self) -> None:
        if not self._sync_engine:
            return

        provider_name = self._provider_combo.currentText()
        if provider_name == "None":
            return

        self._status_label.setText("Connecting...")
        self._connect_btn.setEnabled(False)
        asyncio.ensure_future(self._do_connect(provider_name))

    async def _do_connect(self, provider_name: str) -> None:
        """Full OAuth flow: create provider → start callback → open browser → authenticate."""
        from rlqshell.core.sync.auth_server import OAuthCallbackServer

        proxy_url = self._get_proxy_url()

        try:
            provider = _create_provider(provider_name, proxy_url)
        except ValueError as exc:
            self._status_label.setText(str(exc))
            self._connect_btn.setEnabled(True)
            return

        # Start local OAuth callback server
        callback = OAuthCallbackServer()
        callback.start()

        # Open browser for authorization
        auth_url = provider.get_auth_url()
        webbrowser.open(auth_url)
        self._status_label.setText("Waiting for authorization...")

        # Wait for callback
        code = await callback.wait_for_code(timeout=120)
        if not code:
            self._status_label.setText("Authorization timed out")
            self._connect_btn.setEnabled(True)
            return

        # Exchange code for tokens
        success = await provider.authenticate(code)
        if not success:
            self._status_label.setText("Authentication failed")
            self._connect_btn.setEnabled(True)
            return

        # Persist tokens
        if self._token_store:
            tokens = provider.get_tokens()
            if tokens:
                self._token_store.save_tokens(provider_name, tokens[0], tokens[1])

        # Wire provider into engine
        self._sync_engine.set_provider(provider)
        self._sync_engine.cloud_folder = self._cloud_folder.text().strip()

        # Set up token persistence callback
        if self._token_store:
            self._sync_engine.set_token_save_callback(
                lambda a, r: self._token_store.save_tokens(provider_name, a, r)
            )

        # Start auto-sync if enabled
        if self._config.get("sync.auto_sync", False):
            interval = self._config.get("sync.interval_minutes", 5)
            self._sync_engine.start_auto_sync(interval)

        self._update_status()

    def _on_sync_now(self) -> None:
        if self._sync_engine:
            asyncio.ensure_future(self._sync_engine.sync())

    def _on_disconnect(self) -> None:
        if self._sync_engine and self._sync_engine.provider:
            asyncio.ensure_future(self._sync_engine.provider.disconnect())
            self._sync_engine.stop_auto_sync()

            # Clear persisted tokens
            provider_name = self._provider_combo.currentText()
            if self._token_store:
                self._token_store.clear_tokens(provider_name)

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
            self._status_label.setStyleSheet(
                f"font-size: 12px; color: {Colors.TEXT_MUTED}; background: transparent;"
            )
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


def _create_provider(name: str, proxy_url: str | None = None):
    """Instantiate a cloud provider by name."""
    from rlqshell.app.constants import (
        OAUTH_DROPBOX_APP_KEY,
        OAUTH_GOOGLE_CLIENT_ID,
        OAUTH_ONEDRIVE_CLIENT_ID,
    )

    if name == "OneDrive":
        if not OAUTH_ONEDRIVE_CLIENT_ID:
            raise ValueError("OneDrive Client ID not configured")
        from rlqshell.core.sync.providers.onedrive import OneDriveProvider

        return OneDriveProvider(
            client_id=OAUTH_ONEDRIVE_CLIENT_ID, proxy_url=proxy_url
        )
    elif name == "Google Drive":
        if not OAUTH_GOOGLE_CLIENT_ID:
            raise ValueError("Google Drive Client ID not configured")
        from rlqshell.core.sync.providers.google_drive import GoogleDriveProvider

        return GoogleDriveProvider(
            client_id=OAUTH_GOOGLE_CLIENT_ID, proxy_url=proxy_url
        )
    elif name == "Dropbox":
        if not OAUTH_DROPBOX_APP_KEY:
            raise ValueError("Dropbox App Key not configured")
        from rlqshell.core.sync.providers.dropbox import DropboxProvider

        return DropboxProvider(app_key=OAUTH_DROPBOX_APP_KEY, proxy_url=proxy_url)
    else:
        raise ValueError(f"Unknown provider: {name}")
