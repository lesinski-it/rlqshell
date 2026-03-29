"""Connections page — tabbed terminal sessions."""

from __future__ import annotations

import asyncio
import getpass
import logging
import uuid

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from termplus.app.config import ConfigManager
from termplus.app.constants import Colors
from termplus.core.connection_pool import ConnectionPool
from termplus.core.credential_store import CredentialStore
from termplus.core.history_manager import HistoryManager
from termplus.core.host_manager import HostManager
from termplus.core.keychain import Keychain
from termplus.core.known_hosts import HostKeyStatus, KnownHostsManager
from termplus.core.models.host import Host
from termplus.protocols.base import AbstractConnection
from termplus.protocols.ssh.connection import HostKeyVerifyCallback, SSHConnection
from termplus.protocols.ssh.monitor import ServerMonitor
from termplus.protocols.rdp.connection import RDPConnection
from termplus.protocols.rdp.widget import RDPWidget
from termplus.protocols.vnc.connection import VNCConnection
from termplus.protocols.vnc.widget import VNCWidget
from termplus.ui.connections.detached_window import DetachedTabWindow
from termplus.ui.connections.session_status_bar import SessionStatusBar
from termplus.ui.connections.tab_bar import ConnectionTabBar
from termplus.ui.connections.terminal_widget import TerminalWidget
from termplus.ui.dialogs.host_key_dialog import HostKeyDialog
from termplus.ui.widgets.empty_state import EmptyState
from termplus.ui.widgets.remote_control_panel import RemoteDesktopContainer

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
        config: ConfigManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._host_manager = host_manager
        self._credential_store = credential_store
        self._keychain = keychain
        self._pool = connection_pool
        self._known_hosts = known_hosts
        self._history = history_manager
        self._config = config

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tab bar
        self._tab_bar = ConnectionTabBar()
        self._tab_bar.tab_selected.connect(self._on_tab_selected)
        self._tab_bar.tab_close_requested.connect(self._on_tab_close)
        self._tab_bar.tab_detach_requested.connect(self._on_tab_detach)
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

        # Server monitoring
        self._monitors: dict[str, ServerMonitor] = {}
        self._active_monitor_id: str | None = None  # tab_id of monitor wired to status bar
        monitoring_enabled = config.get("monitoring.enabled", True) if config else True
        self._status_bar = SessionStatusBar()
        self._status_bar.set_monitoring_enabled(monitoring_enabled)
        self._status_bar.monitoring_toggled.connect(self._on_monitoring_toggled)
        layout.addWidget(self._status_bar)

        # Track tab_id → (widget, connection)
        self._sessions: dict[str, tuple[QWidget, AbstractConnection | None]] = {}
        self._detached_windows: dict[str, DetachedTabWindow] = {}
        self._history_records: dict[str, int] = {}  # tab_id → history record id

        self._pool.connection_count_changed.connect(self.connection_count_changed.emit)
        self._host_key_verify_signal.connect(lambda fn: fn())

    _SUPPORTED_PROTOCOLS = {"ssh", "vnc", "rdp"}

    def open_connection(self, host_id: int) -> None:
        """Open a new connection to the given host."""
        host = self._host_manager.get_host(host_id)
        if host is None:
            logger.error("Host %d not found", host_id)
            return

        if host.protocol not in self._SUPPORTED_PROTOCOLS:
            logger.warning("Protocol %s is not yet supported", host.protocol)
            tab_id = str(uuid.uuid4())[:8]
            label = host.label or host.address
            terminal = TerminalWidget()
            self._terminal_stack.addWidget(terminal)
            terminal.show_overlay(
                f"Protocol \"{host.protocol.upper()}\" is not yet supported.",
                color=Colors.WARNING,
            )
            self._sessions[tab_id] = (terminal, None)
            self._tab_bar.add_tab(
                tab_id, label, protocol=host.protocol.upper(),
                color=host.color_label,
            )
            self._terminal_stack.setCurrentWidget(terminal)
            return

        if host.protocol == "vnc":
            self._open_vnc(host)
        elif host.protocol == "rdp":
            self._open_rdp(host)
        else:
            self._open_ssh(host)

    def _open_ssh(self, host: Host) -> None:
        """Open an SSH terminal session."""
        tab_id = str(uuid.uuid4())[:8]
        label = host.label or host.address

        terminal = TerminalWidget()
        self._terminal_stack.addWidget(terminal)

        password, pkey = self._resolve_credentials(host)
        hk_callback = HostKeyVerifyCallback(self._verify_host_key)

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

        conn.data_received.connect(terminal.feed)
        conn.connected.connect(terminal.clear_overlay)
        conn.connected.connect(
            lambda tid=tab_id, c=conn, h=host.address: self._start_monitor(tid, c, h)
        )
        conn.disconnected.connect(lambda tid=tab_id: self._on_disconnected(tid))
        conn.error.connect(lambda msg, tid=tab_id: self._on_error(tid, msg))
        terminal.input_ready.connect(conn.send)
        terminal.size_changed.connect(conn.resize)

        self._sessions[tab_id] = (terminal, conn)
        self._pool.add(tab_id, conn)

        self._tab_bar.add_tab(
            tab_id, label, protocol="SSH", color=host.color_label,
        )
        self._terminal_stack.setCurrentWidget(terminal)
        terminal.setFocus()

        terminal.show_overlay(f"Connecting to {host.address}:{host.ssh_port}...")
        asyncio.ensure_future(self._connect_async(tab_id, conn, host))

    def _open_vnc(self, host: Host) -> None:
        """Open a VNC graphical session."""
        tab_id = str(uuid.uuid4())[:8]
        label = host.label or host.address

        password, _ = self._resolve_credentials(host)

        conn = VNCConnection(
            hostname=host.address,
            port=host.vnc_port,
            password=password,
            view_only=host.vnc_view_only,
        )

        vnc_widget = VNCWidget(conn)
        container = RemoteDesktopContainer(vnc_widget, conn, "vnc")
        self._terminal_stack.addWidget(container)
        container.fullscreen_requested.connect(self._tab_bar.fullscreen_requested)

        conn.connected.connect(container.clear_overlay)
        conn.disconnected.connect(lambda tid=tab_id: self._on_disconnected(tid))
        conn.error.connect(lambda msg, tid=tab_id: self._on_error(tid, msg))

        self._sessions[tab_id] = (container, conn)
        self._pool.add(tab_id, conn)

        self._tab_bar.add_tab(
            tab_id, label, protocol="VNC", color=host.color_label,
        )
        self._terminal_stack.setCurrentWidget(container)
        container.setFocus()

        container.show_overlay(f"Connecting to {host.address}:{host.vnc_port}...")
        asyncio.ensure_future(self._connect_async(tab_id, conn, host))

    def _open_rdp(self, host: Host) -> None:
        """Open an RDP graphical session (pure Python via aardwolf)."""
        tab_id = str(uuid.uuid4())[:8]
        label = host.label or host.address

        password, _ = self._resolve_credentials(host)
        username = host.rdp_username
        if not username and host.ssh_identity_id and self._credential_store.is_unlocked:
            identity = self._credential_store.get_identity(host.ssh_identity_id)
            if identity and identity.username:
                username = identity.username

        # Prompt for credentials if missing
        if not username or not password:
            from termplus.ui.dialogs.rdp_credentials_dialog import RDPCredentialsDialog
            dlg = RDPCredentialsDialog(
                hostname=host.address,
                username=username or "",
                domain=host.rdp_domain or "",
                credential_store=self._credential_store,
                parent=self.window(),
            )
            if dlg.exec() != dlg.DialogCode.Accepted:
                return
            username = dlg.username()
            password = dlg.password()
            host.rdp_domain = dlg.domain() or host.rdp_domain

        conn = RDPConnection(
            hostname=host.address,
            port=host.rdp_port,
            username=username,
            password=password,
            domain=host.rdp_domain,
            resolution=host.rdp_resolution,
            color_depth=host.rdp_color_depth,
            clipboard=host.rdp_clipboard,
        )

        rdp_widget = RDPWidget(conn)
        container = RemoteDesktopContainer(rdp_widget, conn, "rdp")
        self._terminal_stack.addWidget(container)
        container.fullscreen_requested.connect(self._tab_bar.fullscreen_requested)

        conn.connected.connect(container.clear_overlay)
        conn.disconnected.connect(lambda tid=tab_id: self._on_disconnected(tid))
        conn.error.connect(lambda msg, tid=tab_id: self._on_error(tid, msg))

        self._sessions[tab_id] = (container, conn)
        self._pool.add(tab_id, conn)

        self._tab_bar.add_tab(
            tab_id, label, protocol="RDP", color=host.color_label,
        )
        self._terminal_stack.setCurrentWidget(container)
        container.setFocus()

        container.show_overlay(f"Connecting to {host.address}:{host.rdp_port}...")
        asyncio.ensure_future(self._connect_async(tab_id, conn, host))

    async def _connect_async(
        self, tab_id: str, conn: AbstractConnection, host: Host,
    ) -> None:
        """Asynchronously establish the connection."""
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
            logger.error("Connection %s to %s failed: %s", tab_id, host.address, exc)
            session = self._sessions.get(tab_id)
            if session:
                widget, _ = session
                widget.show_overlay(
                    f"Connection to {host.address} failed: {exc}",
                    color=Colors.DANGER,
                )  # type: ignore[union-attr]

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
            widget, _ = session
            self._terminal_stack.setCurrentWidget(widget)
            widget.setFocus()
        self._update_status_bar(tab_id)

    def _on_tab_close(self, tab_id: str) -> None:
        monitor = self._monitors.pop(tab_id, None)
        if monitor:
            monitor.stop()
        session = self._sessions.pop(tab_id, None)
        if session:
            widget, conn = session
            if conn is not None:
                conn.close()
            self._terminal_stack.removeWidget(widget)
            widget.deleteLater()
        # Record disconnect in history
        rec_id = self._history_records.pop(tab_id, None)
        if rec_id and self._history:
            self._history.record_disconnect(rec_id)
        self._pool.remove(tab_id)
        self._tab_bar.remove_tab(tab_id)

        if not self._sessions:
            self._terminal_stack.setCurrentWidget(self._empty_state)
            self._status_bar.clear()
            self._status_bar.setVisible(False)
        else:
            active = self._tab_bar.active_tab
            if active:
                self._update_status_bar(active)

    def _on_disconnected(self, tab_id: str) -> None:
        logger.info("Connection %s disconnected", tab_id)
        monitor = self._monitors.pop(tab_id, None)
        if monitor:
            monitor.stop()
        session = self._sessions.get(tab_id)
        if session:
            widget, _ = session
            widget.show_overlay("Disconnected", color=Colors.WARNING)  # type: ignore[union-attr]
        rec_id = self._history_records.pop(tab_id, None)
        if rec_id and self._history:
            self._history.record_disconnect(rec_id)
        # Refresh status bar — monitor stopped, but SSH tab may still be active
        active = self._tab_bar.active_tab
        if active:
            self._update_status_bar(active)

    def _on_error(self, tab_id: str, message: str) -> None:
        logger.error("Connection %s error: %s", tab_id, message)
        session = self._sessions.get(tab_id)
        if session:
            widget, _ = session
            widget.show_overlay(f"Error: {message}", color=Colors.DANGER)  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    # Server monitoring
    # ------------------------------------------------------------------

    def _start_monitor(self, tab_id: str, conn: SSHConnection, hostname: str) -> None:
        """Start a server monitor for an SSH session after it connects."""
        enabled = self._config.get("monitoring.enabled", True) if self._config else True
        if not enabled or conn.transport is None:
            return
        monitor = ServerMonitor(conn.transport, hostname)
        self._monitors[tab_id] = monitor
        monitor.start()
        # Refresh status bar if this tab is currently active
        session = self._sessions.get(tab_id)
        if session and self._terminal_stack.currentWidget() is session[0]:
            self._update_status_bar(tab_id)

    def _update_status_bar(self, tab_id: str) -> None:
        """Reconnect the status bar to the monitor for the newly active tab."""
        # Disconnect the previously wired monitor (if any)
        if self._active_monitor_id is not None:
            prev = self._monitors.get(self._active_monitor_id)
            if prev is not None:
                prev.stats_updated.disconnect(self._status_bar.update_stats)
            self._active_monitor_id = None

        monitor = self._monitors.get(tab_id)
        if monitor:
            monitor.stats_updated.connect(self._status_bar.update_stats)
            self._active_monitor_id = tab_id

        # Show bar for any active SSH session so the toggle remains accessible.
        session = self._sessions.get(tab_id)
        is_ssh = session is not None and session[1] is not None and session[1].protocol == "ssh"
        self._status_bar.clear()
        self._status_bar.setVisible(is_ssh)

    def _on_monitoring_toggled(self, enabled: bool) -> None:
        """Persist the monitoring toggle state and stop/restart monitors."""
        if self._config:
            self._config.set("monitoring.enabled", enabled)
            self._config.save()
        if not enabled:
            # Disconnect active monitor first
            if self._active_monitor_id is not None:
                prev = self._monitors.get(self._active_monitor_id)
                if prev is not None:
                    prev.stats_updated.disconnect(self._status_bar.update_stats)
                self._active_monitor_id = None
            for monitor in list(self._monitors.values()):
                monitor.stop()
            self._monitors.clear()
        else:
            # Restart monitors for all currently connected SSH sessions
            for tab_id, (_widget, conn) in self._sessions.items():
                if (
                    conn.protocol == "ssh"
                    and conn.is_connected
                    and conn.transport is not None
                    and tab_id not in self._monitors
                ):
                    monitor = ServerMonitor(conn.transport, conn.hostname)
                    self._monitors[tab_id] = monitor
                    monitor.start()
            active = self._tab_bar.active_tab
            if active:
                self._update_status_bar(active)

    # ------------------------------------------------------------------
    # Detach / Dock
    # ------------------------------------------------------------------

    def _on_tab_detach(self, tab_id: str) -> None:
        """Detach a tab into a floating window."""
        session = self._sessions.get(tab_id)
        if not session:
            return
        info = self._tab_bar.tab_info(tab_id)
        if not info:
            return
        label, protocol, color = info
        widget, conn = session

        # Freeze resize to preserve terminal buffer during reparenting
        if hasattr(widget, '_freeze_resize'):
            widget._freeze_resize = True

        # Remove from stack and tab bar (keep session alive)
        self._terminal_stack.removeWidget(widget)
        widget.setParent(None)  # fully detach from old parent
        self._tab_bar.remove_tab(tab_id)

        # Create floating window
        win = DetachedTabWindow(tab_id, label, protocol, color, widget)
        win.dock_requested.connect(self._on_tab_dock)
        win.closed.connect(self._on_detached_close)
        self._detached_windows[tab_id] = win
        win.show()

        # Unfreeze and recalculate after layout settles
        from PySide6.QtCore import QTimer
        QTimer.singleShot(200, lambda w=widget, c=conn: self._refresh_detached(w, c))

        if not self._tab_bar.tab_count:
            self._terminal_stack.setCurrentWidget(self._empty_state)

    @staticmethod
    def _refresh_detached(widget: QWidget, conn: AbstractConnection | None) -> None:
        """Force widget refresh after detaching into a floating window."""
        # Unfreeze resize and recompute for new container size
        if hasattr(widget, '_freeze_resize'):
            widget._freeze_resize = False
            if hasattr(widget, '_recompute_size'):
                widget._recompute_size()
        widget.update()
        # For SSH terminals, resize PTY and send Ctrl+L to force redraw
        if conn and hasattr(widget, '_cols') and hasattr(widget, '_rows'):
            cols, rows = widget._cols, widget._rows
            conn.resize(cols, rows)
            # Ctrl+L forces bash/zsh/vim to redraw the screen
            if hasattr(conn, 'send'):
                conn.send(b'\x0c')

    def _on_tab_dock(self, tab_id: str) -> None:
        """Re-dock a floating window back into the tab bar."""
        win = self._detached_windows.pop(tab_id, None)
        if not win:
            return
        session = self._sessions.get(tab_id)
        if not session:
            win.close_for_dock()
            return

        # Retrieve the content widget from the floating window
        widget = win.dock_back()
        if widget is None:
            win.close_for_dock()
            return

        # Freeze resize during reparenting
        if hasattr(widget, '_freeze_resize'):
            widget._freeze_resize = True

        # Re-add to stack and tab bar
        self._terminal_stack.addWidget(widget)
        self._sessions[tab_id] = (widget, session[1])
        self._tab_bar.add_tab(
            tab_id, win.label_text, protocol=win.protocol,
            color=win.color,
        )
        self._terminal_stack.setCurrentWidget(widget)
        widget.setFocus()

        # Unfreeze and refresh after layout settles
        from PySide6.QtCore import QTimer
        QTimer.singleShot(200, lambda w=widget, c=session[1]: self._refresh_detached(w, c))

        win.close_for_dock()

    def _on_detached_close(self, tab_id: str) -> None:
        """Handle closing of a detached window — full session cleanup."""
        self._detached_windows.pop(tab_id, None)
        session = self._sessions.pop(tab_id, None)
        if session:
            widget, conn = session
            if conn is not None:
                conn.close()
            widget.deleteLater()
        rec_id = self._history_records.pop(tab_id, None)
        if rec_id and self._history:
            self._history.record_disconnect(rec_id)
        self._pool.remove(tab_id)

    def close_current_tab(self) -> None:
        """Close the currently active tab."""
        active = self._tab_bar.active_tab
        if active:
            self._on_tab_close(active)

    def next_tab(self) -> None:
        """Switch to the next tab (visual order)."""
        tab_ids = self._tab_bar.ordered_tab_ids()
        if len(tab_ids) < 2:
            return
        active = self._tab_bar.active_tab
        if active in tab_ids:
            idx = (tab_ids.index(active) + 1) % len(tab_ids)
            self._tab_bar.select_tab(tab_ids[idx])

    def prev_tab(self) -> None:
        """Switch to the previous tab (visual order)."""
        tab_ids = self._tab_bar.ordered_tab_ids()
        if len(tab_ids) < 2:
            return
        active = self._tab_bar.active_tab
        if active in tab_ids:
            idx = (tab_ids.index(active) - 1) % len(tab_ids)
            self._tab_bar.select_tab(tab_ids[idx])

    def send_to_active_terminal(self, script: str) -> bool:
        """Send a script/command to the currently active terminal session.

        Returns True if the command was sent, False if no active session.
        Only works for text-based protocols (SSH, Telnet).
        """
        active = self._tab_bar.active_tab
        if not active or active not in self._sessions:
            return False
        widget, conn = self._sessions[active]
        if conn is None or isinstance(conn, (VNCConnection, RDPConnection)):
            return False
        conn.send(script.encode("utf-8") + b"\n")
        return True

    def set_tab_bar_visible(self, visible: bool) -> None:
        """Show or hide the connection tab bar and status bar (for fullscreen mode)."""
        self._tab_bar.setVisible(visible)
        if not visible:
            self._status_bar.setVisible(False)
        else:
            # Restore status bar visibility based on current active tab
            active = self._tab_bar.active_tab
            if active:
                self._update_status_bar(active)

    def close_all(self) -> None:
        """Close all connections (docked and detached)."""
        for tab_id, win in list(self._detached_windows.items()):
            win.close_for_dock()
            self._detached_windows.pop(tab_id, None)
        for tab_id in list(self._sessions):
            self._on_tab_close(tab_id)
