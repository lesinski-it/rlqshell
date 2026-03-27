"""Connections page — tabbed terminal sessions."""

from __future__ import annotations

import asyncio
import logging
import uuid

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from termplus.app.constants import Colors
from termplus.core.connection_pool import ConnectionPool
from termplus.core.credential_store import CredentialStore
from termplus.core.host_manager import HostManager
from termplus.core.keychain import Keychain
from termplus.core.models.host import Host
from termplus.protocols.ssh.connection import SSHConnection
from termplus.ui.connections.tab_bar import ConnectionTabBar
from termplus.ui.connections.terminal_widget import TerminalWidget
from termplus.ui.widgets.empty_state import EmptyState

logger = logging.getLogger(__name__)


class ConnectionsPage(QWidget):
    """Page managing tabbed terminal connections."""

    connection_count_changed = Signal(int)

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

        # Terminal stack
        self._terminal_stack = QStackedWidget()
        layout.addWidget(self._terminal_stack, 1)

        # Empty state (shown when no tabs)
        self._empty_state = EmptyState(
            title="No Active Connections",
            description="Connect to a host from the Vault to start a terminal session.",
            icon_text="~>_",
        )
        self._terminal_stack.addWidget(self._empty_state)

        # Track tab_id → (terminal, connection)
        self._sessions: dict[str, tuple[TerminalWidget, SSHConnection]] = {}

        self._pool.connection_count_changed.connect(self.connection_count_changed.emit)

    def open_connection(self, host_id: int) -> None:
        """Open a new SSH connection to the given host."""
        host = self._host_manager.get_host(host_id)
        if host is None:
            logger.error("Host %d not found", host_id)
            return

        tab_id = str(uuid.uuid4())[:8]
        label = host.label or host.address

        # Create terminal widget
        terminal = TerminalWidget()
        self._terminal_stack.addWidget(terminal)

        # Resolve credentials
        password, pkey = self._resolve_credentials(host)

        # Create SSH connection
        conn = SSHConnection(
            hostname=host.address,
            port=host.ssh_port,
            username=self._resolve_username(host),
            password=password,
            pkey=pkey,
            keep_alive=host.ssh_keep_alive,
            agent_forwarding=host.ssh_agent_forwarding,
            compression=host.ssh_compression,
        )

        # Wire signals
        conn.data_received.connect(terminal.feed)
        conn.disconnected.connect(lambda tid=tab_id: self._on_disconnected(tid))
        conn.error.connect(lambda msg, tid=tab_id: self._on_error(tid, msg))
        terminal.input_ready.connect(conn.send)
        terminal.size_changed.connect(conn.resize)

        self._sessions[tab_id] = (terminal, conn)
        self._pool.add(tab_id, conn)

        # Add tab and switch to it
        self._tab_bar.add_tab(
            tab_id, label, protocol=host.protocol.upper(),
            color=host.color_label,
        )
        self._terminal_stack.setCurrentWidget(terminal)
        terminal.setFocus()

        # Start connection asynchronously
        asyncio.ensure_future(self._connect_async(tab_id, conn))

    async def _connect_async(self, tab_id: str, conn: SSHConnection) -> None:
        """Asynchronously establish the SSH connection."""
        try:
            await conn.connect()
            logger.info("Connection %s established", tab_id)
        except Exception as exc:
            logger.error("Connection %s failed: %s", tab_id, exc)

    def _resolve_credentials(self, host: Host) -> tuple[str | None, object]:
        """Get password and/or PKey for the host's identity."""
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
        """Get the username from the host's identity or fall back."""
        if host.ssh_identity_id and self._credential_store.is_unlocked:
            identity = self._credential_store.get_identity(host.ssh_identity_id)
            if identity:
                return identity.username
        return ""

    def _on_tab_selected(self, tab_id: str) -> None:
        session = self._sessions.get(tab_id)
        if session:
            terminal, _ = session
            self._terminal_stack.setCurrentWidget(terminal)
            terminal.setFocus()

    def _on_tab_close(self, tab_id: str) -> None:
        session = self._sessions.pop(tab_id, None)
        if session:
            terminal, conn = session
            conn.close()
            self._terminal_stack.removeWidget(terminal)
            terminal.deleteLater()
        self._pool.remove(tab_id)
        self._tab_bar.remove_tab(tab_id)

        if not self._sessions:
            self._terminal_stack.setCurrentWidget(self._empty_state)

    def _on_disconnected(self, tab_id: str) -> None:
        logger.info("Connection %s disconnected", tab_id)

    def _on_error(self, tab_id: str, message: str) -> None:
        logger.error("Connection %s error: %s", tab_id, message)

    def close_all(self) -> None:
        """Close all connections."""
        for tab_id in list(self._sessions):
            self._on_tab_close(tab_id)
