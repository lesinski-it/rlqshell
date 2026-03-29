"""SFTP page — tabbed file browser sessions."""

from __future__ import annotations

import asyncio
import getpass
import logging
import uuid

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMessageBox, QStackedWidget, QVBoxLayout, QWidget

from termplus.app.config import ConfigManager
from termplus.core.connection_pool import ConnectionPool
from termplus.core.credential_store import CredentialStore
from termplus.core.host_manager import HostManager
from termplus.core.keychain import Keychain
from termplus.core.models.host import Host
from termplus.protocols.ssh.connection import SSHConnection
from termplus.protocols.ssh.sftp_session import SFTPSession
from termplus.ui.connections.tab_bar import ConnectionTabBar
from termplus.ui.sftp.file_browser import FileBrowser
from termplus.ui.sftp.transfer_queue import TransferQueue
from termplus.ui.widgets.empty_state import EmptyState
from termplus.ui.widgets.toast import ToastManager

logger = logging.getLogger(__name__)


class SFTPPage(QWidget):
    """Page managing tabbed SFTP sessions."""

    new_session_requested = Signal()
    session_count_changed = Signal(int)

    def __init__(
        self,
        host_manager: HostManager,
        credential_store: CredentialStore,
        keychain: Keychain,
        connection_pool: ConnectionPool,
        config: ConfigManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._host_manager = host_manager
        self._credential_store = credential_store
        self._keychain = keychain
        self._pool = connection_pool
        self._config = config

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tab bar
        self._tab_bar = ConnectionTabBar()
        self._tab_bar.tab_selected.connect(self._on_tab_selected)
        self._tab_bar.tab_close_requested.connect(self._on_tab_close)
        self._tab_bar.new_tab_requested.connect(self.new_session_requested.emit)
        layout.addWidget(self._tab_bar)

        # Browser stack
        self._browser_stack = QStackedWidget()
        layout.addWidget(self._browser_stack, 1)

        # Empty state
        self._empty_state = EmptyState(
            title="No SFTP Sessions",
            description="Connect to a host from the Vault to browse files.",
            icon_text="📂",
        )
        self._browser_stack.addWidget(self._empty_state)

        # Transfer queue
        self._transfer_queue = TransferQueue()
        self._transfer_queue.upload_completed.connect(self._on_upload_completed)
        layout.addWidget(self._transfer_queue)

        # Track sessions: tab_id → (browser, sftp_session, ssh_connection, owns_conn)
        # owns_conn=True means this session created the SSH connection and is responsible for closing it
        self._sessions: dict[str, tuple[FileBrowser, SFTPSession, SSHConnection, bool]] = {}

    def open_sftp_session(self, host_id: int) -> None:
        """Open a new SFTP session to the given host."""
        try:
            host = self._host_manager.get_host(host_id)
            if host is None:
                logger.error("Host %d not found", host_id)
                return

            tab_id = str(uuid.uuid4())[:8]
            label = host.label or host.address

            asyncio.ensure_future(
                self._open_sftp_async(tab_id, label, host)
            )
        except Exception:
            logger.exception("Failed to schedule SFTP session for host %d", host_id)
            ToastManager.instance().show_toast("Failed to open SFTP session.")

    async def _open_sftp_async(
        self,
        tab_id: str,
        label: str,
        host: Host,
    ) -> None:
        try:
            # Only reuse connections from other SFTP sessions (same lifecycle).
            # Never borrow from terminal connections — closing the terminal would
            # kill the transport and break this SFTP session.
            sftp_conn = self._find_sftp_session_connection(host)
            if sftp_conn:
                conn = sftp_conn
                owns_conn = False
            else:
                conn = await self._create_ssh_connection(host)
                owns_conn = True

            if conn.transport is None:
                logger.error("No transport for SFTP")
                return

            sftp = SFTPSession(conn.transport)
            await sftp.open()

            browser = FileBrowser(sftp)
            browser.transfer_requested.connect(
                lambda d, l, r: self._transfer_queue.add_transfer(sftp, d, l, r)
            )
            self._browser_stack.addWidget(browser)

            self._sessions[tab_id] = (browser, sftp, conn, owns_conn)

            self._tab_bar.add_tab(tab_id, label, protocol="SFTP", color=host.color_label, show_fullscreen=False)
            self._browser_stack.setCurrentWidget(browser)
            self.session_count_changed.emit(len(self._sessions))

            await browser.navigate()
            logger.info("SFTP session opened: %s", label)

        except Exception as exc:
            logger.exception("Failed to open SFTP for %s", label)
            ToastManager.instance().show_toast(
                f"SFTP connection failed: {exc}",
            )

    async def _create_ssh_connection(self, host: Host) -> SSHConnection:
        """Create a fresh SSH connection for SFTP (no shell channel needed)."""
        password, pkey = self._resolve_credentials(host)
        conn = SSHConnection(
            hostname=host.address,
            port=host.ssh_port,
            username=self._resolve_username(host),
            password=password,
            pkey=pkey,
            keep_alive=host.ssh_keep_alive,
            compression=host.ssh_compression,
            open_shell=False,
        )
        await conn.connect()
        return conn

    def _resolve_credentials(self, host: Host):
        password = None
        pkey = None
        if host.ssh_identity_id and self._credential_store.is_unlocked:
            identity = self._credential_store.get_identity(host.ssh_identity_id)
            if identity:
                if identity.encrypted_password:
                    password = self._credential_store.decrypt_password(
                        identity.encrypted_password
                    )
                if identity.ssh_key_id:
                    pkey = self._keychain.get_paramiko_pkey(identity.ssh_key_id)
        return password, pkey

    def _resolve_username(self, host: Host) -> str:
        if host.ssh_identity_id and self._credential_store.is_unlocked:
            identity = self._credential_store.get_identity(host.ssh_identity_id)
            if identity and identity.username:
                return identity.username
        return getpass.getuser()

    def _on_upload_completed(self, sftp: SFTPSession) -> None:
        """Refresh the browser that owns the completed upload's SFTP session."""
        for browser, session, *_ in self._sessions.values():
            if session is sftp:
                asyncio.ensure_future(browser.navigate())
                break

    def _find_sftp_session_connection(self, host: Host) -> SSHConnection | None:
        """Find an existing SSH connection already used by another SFTP session."""
        for _, _, conn, _ in self._sessions.values():
            if (
                conn.is_connected
                and conn._hostname == host.address
                and conn._port == host.ssh_port
            ):
                return conn
        return None

    def _on_tab_selected(self, tab_id: str) -> None:
        session = self._sessions.get(tab_id)
        if session:
            browser, *_ = session
            self._browser_stack.setCurrentWidget(browser)

    def _on_tab_close(self, tab_id: str) -> None:
        # Confirm before closing
        confirm = self._config.get("general.confirm_close_tab", True) if self._config else True
        if confirm and tab_id in self._sessions:
            info = self._tab_bar.tab_info(tab_id)
            label = info[0] if info else "this session"
            msg = QMessageBox(self)
            msg.setWindowTitle("Close SFTP Session")
            msg.setText(f"Close SFTP session to {label}?")
            msg.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            msg.setDefaultButton(QMessageBox.StandardButton.No)
            from PySide6.QtWidgets import QCheckBox
            dont_ask = QCheckBox("Don't ask again")
            msg.setCheckBox(dont_ask)
            result = msg.exec()
            if dont_ask.isChecked() and self._config:
                self._config.set("general.confirm_close_tab", False)
                self._config.save()
            if result != QMessageBox.StandardButton.Yes:
                return

        session = self._sessions.pop(tab_id, None)
        if session:
            browser, sftp, conn, owns_conn = session
            asyncio.ensure_future(sftp.close())
            self._browser_stack.removeWidget(browser)
            browser.deleteLater()
            # Close the SSH connection only if we own it and no other tab is using it
            if owns_conn:
                still_used = any(s[2] is conn for s in self._sessions.values())
                if not still_used:
                    conn.close()
        self._tab_bar.remove_tab(tab_id)
        self.session_count_changed.emit(len(self._sessions))

        if not self._sessions:
            self._browser_stack.setCurrentWidget(self._empty_state)

    def close_all(self) -> None:
        for tab_id in list(self._sessions):
            self._on_tab_close(tab_id)
