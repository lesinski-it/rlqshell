"""SFTP page — tabbed file browser sessions."""

from __future__ import annotations

import asyncio
import logging
import uuid

from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

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

logger = logging.getLogger(__name__)


class SFTPPage(QWidget):
    """Page managing tabbed SFTP sessions."""

    def __init__(
        self,
        host_manager: HostManager,
        credential_store: CredentialStore,
        keychain: Keychain,
        connection_pool: ConnectionPool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._host_manager = host_manager
        self._credential_store = credential_store
        self._keychain = keychain
        self._pool = connection_pool

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tab bar
        self._tab_bar = ConnectionTabBar()
        self._tab_bar.tab_selected.connect(self._on_tab_selected)
        self._tab_bar.tab_close_requested.connect(self._on_tab_close)
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
        layout.addWidget(self._transfer_queue)

        # Track sessions: tab_id → (browser, sftp_session, ssh_connection)
        self._sessions: dict[str, tuple[FileBrowser, SFTPSession, SSHConnection]] = {}

    def open_sftp_session(self, host_id: int) -> None:
        """Open a new SFTP session to the given host."""
        host = self._host_manager.get_host(host_id)
        if host is None:
            logger.error("Host %d not found", host_id)
            return

        tab_id = str(uuid.uuid4())[:8]
        label = host.label or host.address

        # Check if there's an existing SSH connection we can reuse
        existing_conn = self._find_existing_connection(host)

        asyncio.ensure_future(
            self._open_sftp_async(tab_id, label, host, existing_conn)
        )

    async def _open_sftp_async(
        self,
        tab_id: str,
        label: str,
        host: Host,
        existing_conn: SSHConnection | None,
    ) -> None:
        try:
            if existing_conn and existing_conn.transport:
                conn = existing_conn
            else:
                conn = await self._create_ssh_connection(host)

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

            self._sessions[tab_id] = (browser, sftp, conn)

            self._tab_bar.add_tab(tab_id, label, protocol="SFTP")
            self._browser_stack.setCurrentWidget(browser)

            await browser.navigate()
            logger.info("SFTP session opened: %s", label)

        except Exception:
            logger.exception("Failed to open SFTP for %s", label)

    async def _create_ssh_connection(self, host: Host) -> SSHConnection:
        """Create a fresh SSH connection for SFTP."""
        password, pkey = self._resolve_credentials(host)
        conn = SSHConnection(
            hostname=host.address,
            port=host.ssh_port,
            username=self._resolve_username(host),
            password=password,
            pkey=pkey,
            keep_alive=host.ssh_keep_alive,
            compression=host.ssh_compression,
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
            if identity:
                return identity.username
        return ""

    def _find_existing_connection(self, host: Host) -> SSHConnection | None:
        """Look for a reusable SSH connection in the pool."""
        # Simple approach: check all connections in the pool
        for conn_id in list(vars(self._pool).get("_connections", {})):
            conn = self._pool.get(conn_id)
            if (
                isinstance(conn, SSHConnection)
                and conn.is_connected
                and conn._hostname == host.address
                and conn._port == host.ssh_port
            ):
                return conn
        return None

    def _on_tab_selected(self, tab_id: str) -> None:
        session = self._sessions.get(tab_id)
        if session:
            browser, _, _ = session
            self._browser_stack.setCurrentWidget(browser)

    def _on_tab_close(self, tab_id: str) -> None:
        session = self._sessions.pop(tab_id, None)
        if session:
            browser, sftp, _ = session
            asyncio.ensure_future(sftp.close())
            self._browser_stack.removeWidget(browser)
            browser.deleteLater()
        self._tab_bar.remove_tab(tab_id)

        if not self._sessions:
            self._browser_stack.setCurrentWidget(self._empty_state)

    def close_all(self) -> None:
        for tab_id in list(self._sessions):
            self._on_tab_close(tab_id)
