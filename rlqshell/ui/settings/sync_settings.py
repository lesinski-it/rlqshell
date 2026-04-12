"""Sync settings — provider selection, connect/disconnect, status, proxy."""

from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.config import ConfigManager
from rlqshell.app.constants import Colors
from rlqshell.ui.widgets.toggle_switch import ToggleSwitch

logger = logging.getLogger(__name__)

_LABEL_MIN_W = 120


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

        # Outer layout — scroll area
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(6)

        # --- Title ---
        title = QLabel("Cloud Sync")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        layout.addWidget(title)

        desc = QLabel(
            "Sync your hosts, keys, and settings across devices via "
            "cloud storage. Data is encrypted before upload."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_SECONDARY}; "
            f"background: transparent; margin-bottom: 4px;"
        )
        layout.addWidget(desc)

        # === Connection section ===
        layout.addWidget(self._section_label("Connection"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.setColumnMinimumWidth(0, _LABEL_MIN_W)
        grid.setColumnStretch(1, 1)
        row = 0

        # Provider
        grid.addWidget(self._make_label("Provider"), row, 0, Qt.AlignmentFlag.AlignRight)
        self._provider_combo = QComboBox()
        self._provider_combo.addItems(["None", "OneDrive", "Google Drive", "Dropbox"])
        self._provider_combo.setCurrentText(config.get("sync.provider", "None"))
        self._provider_combo.currentTextChanged.connect(self._on_provider_changed)
        grid.addWidget(self._provider_combo, row, 1)
        row += 1

        # Cloud folder
        grid.addWidget(
            self._make_label("Cloud Folder"), row, 0, Qt.AlignmentFlag.AlignRight
        )
        folder_col = QVBoxLayout()
        folder_col.setSpacing(2)
        self._cloud_folder = QLineEdit()
        self._cloud_folder.setText(config.get("sync.cloud_folder", "/RLQShell"))
        self._cloud_folder.setPlaceholderText("/RLQShell")
        self._cloud_folder.editingFinished.connect(self._on_cloud_folder_changed)
        folder_col.addWidget(self._cloud_folder)
        hint = QLabel("Folder will be created automatically if it doesn't exist.")
        hint.setStyleSheet(
            f"font-size: 10px; color: {Colors.TEXT_MUTED}; background: transparent;"
        )
        folder_col.addWidget(hint)
        grid.addLayout(folder_col, row, 1)
        row += 1

        layout.addLayout(grid)

        # === Sync behavior section ===
        layout.addWidget(self._section_label("Behavior"))

        grid2 = QGridLayout()
        grid2.setHorizontalSpacing(12)
        grid2.setVerticalSpacing(8)
        grid2.setColumnMinimumWidth(0, _LABEL_MIN_W)
        grid2.setColumnStretch(1, 1)
        row = 0

        # Auto sync
        grid2.addWidget(
            self._make_label("Auto Sync"), row, 0, Qt.AlignmentFlag.AlignRight
        )
        self._auto_sync = ToggleSwitch()
        self._auto_sync.set_checked(config.get("sync.auto_sync", False))
        self._auto_sync.toggled.connect(lambda v: self._save("sync.auto_sync", v))
        grid2.addWidget(self._auto_sync, row, 1, Qt.AlignmentFlag.AlignLeft)
        row += 1

        # Sync interval
        grid2.addWidget(
            self._make_label("Sync Interval"), row, 0, Qt.AlignmentFlag.AlignRight
        )
        self._interval = QSpinBox()
        self._interval.setRange(1, 60)
        self._interval.setSuffix(" min")
        self._interval.setFixedWidth(100)
        self._interval.setValue(config.get("sync.interval_minutes", 5))
        self._interval.valueChanged.connect(
            lambda v: self._save("sync.interval_minutes", v)
        )
        grid2.addWidget(self._interval, row, 1, Qt.AlignmentFlag.AlignLeft)
        row += 1

        # Sync on startup
        grid2.addWidget(
            self._make_label("Sync on Startup"), row, 0, Qt.AlignmentFlag.AlignRight
        )
        self._sync_on_start = ToggleSwitch()
        self._sync_on_start.set_checked(config.get("sync.sync_on_start", False))
        self._sync_on_start.toggled.connect(
            lambda v: self._save("sync.sync_on_start", v)
        )
        grid2.addWidget(self._sync_on_start, row, 1, Qt.AlignmentFlag.AlignLeft)
        row += 1

        # Sync on close
        grid2.addWidget(
            self._make_label("Sync on Close"), row, 0, Qt.AlignmentFlag.AlignRight
        )
        self._sync_on_close = ToggleSwitch()
        self._sync_on_close.set_checked(config.get("sync.sync_on_close", False))
        self._sync_on_close.toggled.connect(
            lambda v: self._save("sync.sync_on_close", v)
        )
        grid2.addWidget(self._sync_on_close, row, 1, Qt.AlignmentFlag.AlignLeft)
        row += 1

        # Conflict strategy
        grid2.addWidget(
            self._make_label("Conflict Strategy"), row, 0, Qt.AlignmentFlag.AlignRight
        )
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
        grid2.addWidget(self._conflict_combo, row, 1)
        row += 1

        layout.addLayout(grid2)

        # === Proxy section ===
        layout.addWidget(self._section_label("Proxy"))

        grid3 = QGridLayout()
        grid3.setHorizontalSpacing(12)
        grid3.setVerticalSpacing(8)
        grid3.setColumnMinimumWidth(0, _LABEL_MIN_W)
        grid3.setColumnStretch(1, 1)

        grid3.addWidget(
            self._make_label("Use Proxy"), 0, 0, Qt.AlignmentFlag.AlignRight
        )
        self._proxy_toggle = ToggleSwitch()
        self._proxy_toggle.set_checked(config.get("sync.proxy_enabled", False))
        self._proxy_toggle.toggled.connect(self._on_proxy_toggled)
        grid3.addWidget(self._proxy_toggle, 0, 1, Qt.AlignmentFlag.AlignLeft)

        grid3.addWidget(
            self._make_label("Proxy URL"), 1, 0, Qt.AlignmentFlag.AlignRight
        )
        self._proxy_url = QLineEdit()
        self._proxy_url.setText(config.get("sync.proxy_url", ""))
        self._proxy_url.setPlaceholderText("http://proxy.corp.com:8080")
        self._proxy_url.setEnabled(config.get("sync.proxy_enabled", False))
        self._proxy_url.editingFinished.connect(
            lambda: self._save("sync.proxy_url", self._proxy_url.text().strip())
        )
        grid3.addWidget(self._proxy_url, 1, 1)

        layout.addLayout(grid3)

        # === Status + buttons ===
        layout.addSpacing(8)

        self._status_label = QLabel("Not connected")
        self._status_label.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_MUTED}; background: transparent;"
        )
        layout.addWidget(self._status_label)

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

        scroll.setWidget(content)
        outer.addWidget(scroll)

        self._update_status()

    # --- Helpers ---

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent; margin-top: 10px; margin-bottom: 2px;"
        )
        return lbl

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setMinimumWidth(_LABEL_MIN_W)
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

        if provider_name == "OneDrive":
            self._do_connect_device_code(provider_name)
        else:
            asyncio.ensure_future(self._do_connect_redirect(provider_name))

    def _do_connect_device_code(self, provider_name: str) -> None:
        """Device Code Flow (OneDrive Personal)."""
        from rlqshell.ui.dialogs.device_code_dialog import DeviceCodeDialog

        proxy_url = self._get_proxy_url()

        try:
            provider = _create_provider(provider_name, proxy_url)
        except ValueError as exc:
            self._status_label.setText(str(exc))
            self._connect_btn.setEnabled(True)
            return
        except Exception as exc:
            logger.exception("Failed to initialize sync provider %s", provider_name)
            self._status_label.setText(f"Provider initialization failed: {exc}")
            self._connect_btn.setEnabled(True)
            return

        dlg = DeviceCodeDialog(provider, parent=self.window())
        if dlg.exec() == DeviceCodeDialog.DialogCode.Accepted:
            self._finish_connect(provider_name, provider)
        else:
            self._status_label.setText("Authentication cancelled")
            self._connect_btn.setEnabled(True)

    async def _do_connect_redirect(self, provider_name: str) -> None:
        """Browser redirect OAuth flow (Google Drive, Dropbox)."""
        import webbrowser

        from rlqshell.core.sync.auth_server import OAuthCallbackServer

        proxy_url = self._get_proxy_url()

        try:
            provider = _create_provider(provider_name, proxy_url)
        except ValueError as exc:
            self._status_label.setText(str(exc))
            self._connect_btn.setEnabled(True)
            return
        except Exception as exc:
            logger.exception("Failed to initialize sync provider %s", provider_name)
            self._status_label.setText(f"Provider initialization failed: {exc}")
            self._connect_btn.setEnabled(True)
            return

        callback = OAuthCallbackServer()
        callback.start()

        auth_url = provider.get_auth_url()
        webbrowser.open(auth_url)
        self._status_label.setText("Waiting for authorization...")

        code = await callback.wait_for_code(timeout=120)
        if not code:
            self._status_label.setText("Authorization timed out")
            self._connect_btn.setEnabled(True)
            return

        success = await provider.authenticate(code)
        if not success:
            self._status_label.setText("Authentication failed")
            self._connect_btn.setEnabled(True)
            return

        self._finish_connect(provider_name, provider)

    def _finish_connect(self, provider_name: str, provider) -> None:
        """Common post-authentication setup for all providers."""
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
