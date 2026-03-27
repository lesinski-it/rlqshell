"""Connections page — tabbed terminal sessions."""

from __future__ import annotations

import asyncio
import getpass
import logging
import uuid

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from termplus.app.constants import Colors
from termplus.core.connection_pool import ConnectionPool
from termplus.core.credential_store import CredentialStore
from termplus.core.history_manager import HistoryManager
from termplus.core.host_manager import HostManager
from termplus.core.keychain import Keychain
from termplus.core.known_hosts import HostKeyStatus, KnownHostsManager
from termplus.core.models.host import Host
from termplus.protocols.ssh.connection import HostKeyVerifyCallback, SSHConnection
from termplus.ui.connections.tab_bar import ConnectionTabBar
from termplus.ui.connections.terminal_widget import TerminalWidget
from termplus.ui.dialogs.host_key_dialog import HostKeyDialog
from termplus.ui.widgets.empty_state import EmptyState

logger = logging.getLogger(__name__)


class ConnectionsPage(QWidget):
    """Page managing tabbed terminal connections."""

    connection_count_changed = Signal(int)
    _host_key_verify_signal = Signal(object)  # callable

    def __init__(
        self,
        host_manager: HostManager,
        credential_store: CredentialStore,
        keychain: Keychain,
        connection_pool: ConnectionPool,
        known_hosts: KnownHostsManager | None = None,
        history_manager: HistoryManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._host_manager = host_manager
        self._credential_store = credential_store
        self._keychain = keychain
        self._pool = connection_pool
        self._known_hosts = known_hosts
        self._history = history_manager

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
        self._history_records: dict[str, int] = {}  # tab_id → history record id

        self._pool.connection_count_changed.connect(self.connection_count_changed.emit)
        self._host_key_verify_signal.connect(lambda fn: fn())

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

        # Host key verification callback
        hk_callback = HostKeyVerifyCallback(self._verify_host_key)

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
            host_key_callback=hk_callback,
        )

        # Wire signals
        conn.data_received.connect(terminal.feed)
        conn.connected.connect(terminal.clear_overlay)
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

        # Show connecting status
        terminal.show_overlay(f"Connecting to {host.address}:{host.ssh_port}...")

        # Start connection asynchronously
        asyncio.ensure_future(self._connect_async(tab_id, conn, host))

    async def _connect_async(self, tab_id: str, conn: SSHConnection, host: Host) -> None:
        """Asynchronously establish the SSH connection."""
        try:
            await conn.connect()
            logger.info("Connection %s established", tab_id)
            if self._history:
                rec_id = self._history.record_connect(
                    host.id, host.label or host.address,
                    host.address, host.protocol,
                )
                self._history_records[tab_id] = rec_id
        except Exception as exc:
            logger.error("Connection %s failed: %s", tab_id, exc)
            session = self._sessions.get(tab_id)
            if session:
                terminal, _ = session
                terminal.show_overlay(f"Connection failed: {exc}", color=Colors.DANGER)

    def _verify_host_key(
        self, hostname: str, port: int, key_type: str, fingerprint: str,
    ) -> bool:
        """Verify host key — called from background thread, shows dialog on main thread."""
        if self._known_hosts is None:
            return True  # no known hosts manager → auto-accept

        status = self._known_hosts.verify_host_key(hostname, port, key_type, fingerprint)

        if status == HostKeyStatus.MATCH:
            return True

        # Show dialog on main thread, block this thread until user decides
        import threading

        result = [False]
        event = threading.Event()

        def _show_dialog():
            is_mismatch = status == HostKeyStatus.MISMATCH
            dialog = HostKeyDialog(
                hostname, port, key_type, fingerprint,
                is_mismatch=is_mismatch, parent=self.window(),
            )
            accepted = dialog.exec() == HostKeyDialog.DialogCode.Accepted
            if accepted and self._known_hosts:
                self._known_hosts.add_host_key(
                    hostname, port, key_type, fingerprint,
                )
            result[0] = accepted
            event.set()

        # Schedule on main thread via signal
        self._host_key_verify_signal.emit(_show_dialog)
        event.wait(timeout=120)
        return result[0]

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
        """Get the username from the host's identity or fall back to OS user."""
        if host.ssh_identity_id and self._credential_store.is_unlocked:
            identity = self._credential_store.get_identity(host.ssh_identity_id)
            if identity and identity.username:
                return identity.username
        return getpass.getuser()

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
        # Record disconnect in history
        rec_id = self._history_records.pop(tab_id, None)
        if rec_id and self._history:
            self._history.record_disconnect(rec_id)
        self._pool.remove(tab_id)
        self._tab_bar.remove_tab(tab_id)

        if not self._sessions:
            self._terminal_stack.setCurrentWidget(self._empty_state)

    def _on_disconnected(self, tab_id: str) -> None:
        logger.info("Connection %s disconnected", tab_id)
        session = self._sessions.get(tab_id)
        if session:
            terminal, _ = session
            terminal.show_overlay("Disconnected", color=Colors.WARNING)
        rec_id = self._history_records.pop(tab_id, None)
        if rec_id and self._history:
            self._history.record_disconnect(rec_id)

    def _on_error(self, tab_id: str, message: str) -> None:
        logger.error("Connection %s error: %s", tab_id, message)
        session = self._sessions.get(tab_id)
        if session:
            terminal, _ = session
            terminal.show_overlay(f"Error: {message}", color=Colors.DANGER)

    def close_current_tab(self) -> None:
        """Close the currently active tab."""
        active = self._tab_bar.active_tab
        if active:
            self._on_tab_close(active)

    def next_tab(self) -> None:
        """Switch to the next tab."""
        tab_ids = list(self._sessions.keys())
        if len(tab_ids) < 2:
            return
        active = self._tab_bar.active_tab
        if active in tab_ids:
            idx = (tab_ids.index(active) + 1) % len(tab_ids)
            self._tab_bar.select_tab(tab_ids[idx])

    def prev_tab(self) -> None:
        """Switch to the previous tab."""
        tab_ids = list(self._sessions.keys())
        if len(tab_ids) < 2:
            return
        active = self._tab_bar.active_tab
        if active in tab_ids:
            idx = (tab_ids.index(active) - 1) % len(tab_ids)
            self._tab_bar.select_tab(tab_ids[idx])

    def close_all(self) -> None:
        """Close all connections."""
        for tab_id in list(self._sessions):
            self._on_tab_close(tab_id)
