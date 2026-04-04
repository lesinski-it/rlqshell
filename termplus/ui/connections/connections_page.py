"""Connections page — tabbed terminal sessions."""

from __future__ import annotations

import asyncio
import getpass
import logging
import uuid

from PySide6.QtCore import QRect, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QMessageBox, QStackedWidget, QVBoxLayout, QWidget

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
from termplus.ui.connections.split_container import SplitContainer, SplitPanel
from termplus.ui.connections.split_picker import SplitPickerDialog
from termplus.ui.connections.terminal_widget import TerminalWidget
from termplus.ui.dialogs.host_key_dialog import HostKeyDialog
from termplus.ui.widgets.empty_state import EmptyState
from termplus.ui.widgets.remote_control_panel import RemoteDesktopContainer

logger = logging.getLogger(__name__)

_TAB_MIME = "application/x-termplus-tab"


class _DropZoneOverlay(QWidget):
    """Transparent overlay that shows drop zone indicators when dragging a tab.

    Divides the area into left/right (vertical split) and top/bottom (horizontal split)
    quadrants. The hovered quadrant is highlighted with an accent color.
    """

    drop_requested = Signal(str)  # "left", "right", "top", "bottom"

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setVisible(False)
        self._zone: str | None = None  # hovered zone

    def _zone_at(self, pos) -> str:
        w, h = self.width(), self.height()
        x, y = pos.x(), pos.y()
        # Determine zone by which edge the cursor is closest to
        margins = {
            "left": x,
            "right": w - x,
            "top": y,
            "bottom": h - y,
        }
        return min(margins, key=margins.get)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(_TAB_MIME):
            event.acceptProposedAction()
            self._zone = self._zone_at(event.position().toPoint())
            self.update()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(_TAB_MIME):
            event.acceptProposedAction()
            new_zone = self._zone_at(event.position().toPoint())
            if new_zone != self._zone:
                self._zone = new_zone
                self.update()

    def dragLeaveEvent(self, event) -> None:
        self._zone = None
        self.setVisible(False)

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasFormat(_TAB_MIME):
            return
        event.acceptProposedAction()
        zone = self._zone_at(event.position().toPoint())
        self._zone = None
        self.setVisible(False)
        self.drop_requested.emit(zone)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        accent = QColor(Colors.ACCENT)
        accent.setAlpha(40)
        accent_strong = QColor(Colors.ACCENT)
        accent_strong.setAlpha(100)
        border = QColor(Colors.ACCENT)
        border.setAlpha(180)

        # Draw semi-transparent background
        p.fillRect(self.rect(), QColor(0, 0, 0, 60))

        # Draw the hovered zone highlight
        zone = self._zone
        zones = {
            "left": QRect(0, 0, w // 2, h),
            "right": QRect(w // 2, 0, w - w // 2, h),
            "top": QRect(0, 0, w, h // 2),
            "bottom": QRect(0, h // 2, w, h - h // 2),
        }

        if zone and zone in zones:
            rect = zones[zone]
            p.fillRect(rect, accent_strong)
            pen = QPen(border, 2)
            p.setPen(pen)
            p.drawRect(rect.adjusted(1, 1, -1, -1))

            # Draw label
            labels = {"left": "\u258e Split Left", "right": "Split Right \u2590",
                       "top": "\u2580 Split Top", "bottom": "Split Bottom \u2584"}
            p.setPen(QColor(Colors.TEXT_PRIMARY))
            p.setFont(p.font())
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, labels.get(zone, ""))

        p.end()


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
        self._tab_bar.split_requested.connect(lambda: self.show_split_picker())
        self._tab_bar.broadcast_toggled.connect(self._on_broadcast_btn_toggled)
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
        self._tab_host_ids: dict[str, int] = {}  # tab_id → host_id (for split-clone)
        self._split_sub_conns: dict[str, list[tuple[str, AbstractConnection]]] = {}  # tab_id → [(sub_id, conn)]

        self._pool.connection_count_changed.connect(self.connection_count_changed.emit)
        self._host_key_verify_signal.connect(lambda fn: fn())

        # Split picker dialog (lazy-created on first use)
        self._split_picker: SplitPickerDialog | None = None
        self._pending_split_orientation: Qt.Orientation | None = None

        # Drop zone overlay for tab drag-to-split
        self._drop_overlay = _DropZoneOverlay(self._terminal_stack)
        self._drop_overlay.drop_requested.connect(self._on_drop_zone_split)
        self._terminal_stack.setAcceptDrops(True)
        self._terminal_stack.installEventFilter(self)

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
        self._pool.add(tab_id, conn, host_id=host.id)
        self._tab_host_ids[tab_id] = host.id

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
        self._pool.add(tab_id, conn, host_id=host.id)

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
        self._pool.add(tab_id, conn, host_id=host.id)

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
            # Sync broadcast button with current tab's split state
            if isinstance(widget, SplitContainer):
                self._tab_bar.set_broadcast_button_visible(True)
                self._tab_bar.set_broadcast_button_checked(widget.broadcast_mode)
                self._tab_bar._update_broadcast_btn_style(widget.broadcast_mode)
            else:
                self._tab_bar.set_broadcast_button_visible(False)
        self._update_status_bar(tab_id)

    def _on_tab_close(self, tab_id: str) -> None:
        # Confirm before closing an active connection
        confirm = self._config.get("general.confirm_close_tab", True) if self._config else True
        session = self._sessions.get(tab_id)
        if confirm and session and session[1] is not None and session[1].is_connected:
            info = self._tab_bar.tab_info(tab_id)
            label = info[0] if info else "this host"
            msg = QMessageBox(self)
            msg.setWindowTitle("Close Connection")
            msg.setText(f"Disconnect from {label}?")
            msg.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            msg.setDefaultButton(QMessageBox.StandardButton.No)
            cb = msg.checkBox()
            from PySide6.QtWidgets import QCheckBox
            dont_ask = QCheckBox("Don't ask again")
            msg.setCheckBox(dont_ask)
            result = msg.exec()
            if dont_ask.isChecked() and self._config:
                self._config.set("general.confirm_close_tab", False)
                self._config.save()
            if result != QMessageBox.StandardButton.Yes:
                return

        monitor = self._monitors.pop(tab_id, None)
        if monitor:
            monitor.stop()
        # Close sub-connections from split panels
        for sub_id, sub_conn in self._split_sub_conns.pop(tab_id, []):
            sub_conn.close()
            self._pool.remove(sub_id)
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
        self._tab_host_ids.pop(tab_id, None)
        self._tab_bar.remove_tab(tab_id)

        if not self._sessions:
            self._terminal_stack.setCurrentWidget(self._empty_state)
            self._status_bar.clear()
            self._status_bar.setVisible(False)
            self._tab_bar.set_broadcast_button_visible(False)
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
        self._freeze_all_terminals(widget, True)

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
        QTimer.singleShot(200, lambda w=widget, c=conn: self._refresh_detached(w, c))

        if not self._tab_bar.tab_count:
            self._terminal_stack.setCurrentWidget(self._empty_state)

    @staticmethod
    def _refresh_detached(widget: QWidget, conn: AbstractConnection | None) -> None:
        """Force widget refresh after detaching into a floating window."""
        ConnectionsPage._freeze_all_terminals(widget, False)
        widget.update()
        if isinstance(widget, SplitContainer):
            # Refresh each panel's terminal
            for panel in widget.panels:
                t = panel.terminal
                t._recompute_size()
                t.update()
                if panel.connection and hasattr(panel.connection, 'resize'):
                    panel.connection.resize(t._cols, t._rows)
                    if (
                        hasattr(panel.connection, 'send')
                        and ConnectionsPage._terminal_needs_redraw(t)
                    ):
                        panel.connection.send(b'\x0c')
        else:
            # For SSH terminals, resize PTY. Send Ctrl+L only if viewport is blank.
            if conn and hasattr(widget, '_cols') and hasattr(widget, '_rows'):
                cols, rows = widget._cols, widget._rows
                conn.resize(cols, rows)
                if hasattr(conn, 'send') and ConnectionsPage._terminal_needs_redraw(widget):
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
        self._freeze_all_terminals(widget, True)

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
        QTimer.singleShot(200, lambda w=widget, c=session[1]: self._refresh_detached(w, c))

        win.close_for_dock()

    def _on_detached_close(self, tab_id: str) -> None:
        """Handle closing of a detached window — full session cleanup."""
        self._detached_windows.pop(tab_id, None)
        # Close sub-connections from split panels
        for sub_id, sub_conn in self._split_sub_conns.pop(tab_id, []):
            sub_conn.close()
            self._pool.remove(sub_id)
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
        self._tab_host_ids.pop(tab_id, None)

    # ------------------------------------------------------------------
    # Split view & Broadcast
    # ------------------------------------------------------------------

    def split_vertical(self) -> None:
        """Split the active terminal vertically (side by side)."""
        self._show_split_picker(Qt.Orientation.Horizontal)

    def split_horizontal(self) -> None:
        """Split the active terminal horizontally (top / bottom)."""
        self._show_split_picker(Qt.Orientation.Vertical)

    def show_split_picker(self, default_orientation: str = "vertical") -> None:
        """Open the split picker dialog (called from Ctrl+\\ shortcut)."""
        orient = (
            Qt.Orientation.Horizontal if default_orientation == "vertical"
            else Qt.Orientation.Vertical
        )
        self._show_split_picker(orient)

    def _show_split_picker(self, orientation: Qt.Orientation) -> None:
        """Show the fuzzy search split picker for host selection."""
        active = self._tab_bar.active_tab
        if not active or active not in self._sessions:
            return
        _, conn = self._sessions[active]
        if conn is None or conn.protocol != "ssh":
            return
        if self._tab_host_ids.get(active) is None:
            return

        # Store requested orientation for when the picker returns
        self._pending_split_orientation = orientation

        # Build host data for the picker
        hosts = [h for h in self._host_manager.list_hosts(protocol="ssh") if h.id is not None]
        if not hosts:
            from termplus.ui.widgets.toast import ToastManager
            ToastManager.instance().show_toast(
                "No SSH hosts available in Vault.", toast_type="warning",
            )
            return

        # If only one host, skip the picker
        if len(hosts) == 1:
            self._on_split_host_picked(hosts[0].id, "vertical" if orientation == Qt.Orientation.Horizontal else "horizontal")
            return

        groups = {g.id: g.name for g in self._host_manager.list_groups() if g.id is not None}

        host_dicts = []
        for h in hosts:
            host_dicts.append({
                "id": h.id,
                "label": h.label,
                "address": h.address,
                "protocol": h.protocol,
                "group_id": h.group_id,
                "tags": [t.name for t in h.tags],
                "color": h.color_label,
                "last_connected": str(h.last_connected) if h.last_connected else None,
                "connect_count": h.connect_count,
            })

        # Lazy-create picker on first use (window() is available now)
        if self._split_picker is None:
            self._split_picker = SplitPickerDialog(self.window())
            self._split_picker.host_picked.connect(self._on_split_host_picked)

        self._split_picker.setParent(self.window())
        self._split_picker.set_hosts(host_dicts, groups)

        # Set default orientation in picker
        orient_str = "vertical" if orientation == Qt.Orientation.Horizontal else "horizontal"
        self._split_picker._set_orientation(orient_str)

        self._split_picker.show_picker()

    def _on_split_host_picked(self, host_id: int, orientation_str: str) -> None:
        """Handle host selection from the split picker."""
        orientation = (
            Qt.Orientation.Horizontal if orientation_str == "vertical"
            else Qt.Orientation.Vertical
        )

        host = self._host_manager.get_host(host_id)
        if host is None:
            return

        active = self._tab_bar.active_tab
        if not active or active not in self._sessions:
            return

        widget, conn = self._sessions[active]
        if conn is None or conn.protocol != "ssh":
            return
        base_host_id = self._tab_host_ids.get(active)
        if base_host_id is None:
            return

        wrapped_existing_terminal = False
        froze_existing_terminals = False

        base_host = self._host_manager.get_host(base_host_id)
        tab_info = self._tab_bar.tab_info(active)
        base_label = (
            (base_host.label or base_host.address)
            if base_host is not None
            else (tab_info[0] if tab_info else "SSH Session")
        )

        # Create new terminal + connection for the new panel
        new_terminal = TerminalWidget()
        new_terminal._freeze_resize = True
        password, pkey = self._resolve_credentials(host)
        hk_callback = HostKeyVerifyCallback(self._verify_host_key)
        new_conn = SSHConnection(
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
        new_conn.data_received.connect(new_terminal.feed)
        new_conn.connected.connect(new_terminal.clear_overlay)
        new_conn.disconnected.connect(
            lambda t=new_terminal: t.show_overlay("Disconnected", color=Colors.WARNING)
        )
        new_conn.error.connect(
            lambda msg, t=new_terminal: t.show_overlay(f"Error: {msg}", color=Colors.DANGER)
        )
        new_terminal.input_ready.connect(new_conn.send)
        new_terminal.size_changed.connect(new_conn.resize)

        label = host.label or host.address

        if isinstance(widget, SplitContainer):
            container = widget
            self._freeze_all_terminals(container, True)
            froze_existing_terminals = True
        else:
            assert isinstance(widget, TerminalWidget)
            wrapped_existing_terminal = True
            widget._freeze_resize = True
            self._terminal_stack.removeWidget(widget)
            container = SplitContainer(widget, conn, base_host_id, base_label)
            container.all_panels_closed.connect(
                lambda tid=active: self._on_tab_close(tid)
            )
            container.panel_removed.connect(
                lambda panel_id, tid=active: self._on_split_panel_removed(tid, panel_id)
            )
            container.single_panel_remaining.connect(
                lambda panel, tid=active: self._unwrap_split_container(tid, panel)
            )
            container.broadcast_toggled.connect(self._on_broadcast_state_changed)
            self._terminal_stack.addWidget(container)
            self._terminal_stack.setCurrentWidget(container)
            self._sessions[active] = (container, conn)
            widget.show()

        # Show broadcast button now that we have a split container
        self._tab_bar.set_broadcast_button_visible(True)

        panel = container.split(orientation, new_terminal, new_conn, host.id, label)
        if panel is None:
            if wrapped_existing_terminal or froze_existing_terminals:
                self._freeze_all_terminals(container, False)
            new_terminal._freeze_resize = False
            new_conn.close()
            return

        QTimer.singleShot(120, lambda c=container: self._refresh_split_layout(c))
        QTimer.singleShot(320, lambda c=container: self._refresh_split_layout(c))

        sub_id = f"{active}:{panel.panel_id}"
        self._pool.add(sub_id, new_conn, host_id=host.id)
        subs = self._split_sub_conns.setdefault(active, [])
        subs.append((sub_id, new_conn))

        new_terminal.show_overlay(f"Connecting to {host.address}:{host.ssh_port}...")
        asyncio.ensure_future(self._connect_split_async(new_conn, host))

    @staticmethod
    def _refresh_split_layout(container: SplitContainer) -> None:
        """Recompute panel sizes and redraw only blank panels after split settle."""
        for panel in container.panels:
            terminal = panel.terminal
            terminal.show()
            terminal._freeze_resize = False
            terminal._recompute_size()
            terminal.update()

            conn = panel.connection
            if conn is None:
                continue
            if hasattr(conn, "resize") and hasattr(terminal, "_cols") and hasattr(terminal, "_rows"):
                conn.resize(terminal._cols, terminal._rows)
            if hasattr(conn, "send") and ConnectionsPage._terminal_needs_redraw(terminal):
                try:
                    conn.send(b"\x0c")
                except Exception:
                    logger.debug("Redraw send failed for split panel %s", panel.panel_id)

    @staticmethod
    def _terminal_needs_redraw(widget: QWidget) -> bool:
        """Heuristic: redraw only when the terminal viewport is visually empty."""
        if not isinstance(widget, TerminalWidget):
            return False
        if not hasattr(widget, "_get_visible_lines"):
            return False
        try:
            for line in widget._get_visible_lines():
                for char in line.values():
                    data = getattr(char, "data", "")
                    if data and data.strip():
                        return False
        except Exception:
            return False
        return True

    def _on_split_panel_removed(self, tab_id: str, panel_id: str) -> None:
        """Remove split sub-connection bookkeeping when panel is closed from header."""
        sub_id = f"{tab_id}:{panel_id}"
        subs = self._split_sub_conns.get(tab_id)
        if not subs:
            return
        remaining = [(sid, conn) for sid, conn in subs if sid != sub_id]
        if len(remaining) != len(subs):
            self._pool.remove(sub_id)
            if remaining:
                self._split_sub_conns[tab_id] = remaining
            else:
                self._split_sub_conns.pop(tab_id, None)

    def _unwrap_split_container(self, tab_id: str, surviving_panel: object) -> None:
        """Replace SplitContainer with the lone surviving terminal widget."""
        if not isinstance(surviving_panel, SplitPanel):
            return
        session = self._sessions.get(tab_id)
        if not session:
            return
        container, main_conn = session
        if not isinstance(container, SplitContainer):
            return

        terminal = surviving_panel.terminal
        conn = surviving_panel.connection

        # Freeze terminal to avoid pyte buffer corruption during reparenting
        terminal._freeze_resize = True

        # Detach terminal from the SplitPanel before destroying the container
        terminal.setParent(None)

        # Remove container from stack and destroy it
        self._terminal_stack.removeWidget(container)
        container.deleteLater()

        # Re-add the bare terminal to the stack
        self._terminal_stack.addWidget(terminal)
        self._terminal_stack.setCurrentWidget(terminal)
        terminal.show()

        # Update session — use the surviving panel's connection (or original main_conn)
        effective_conn = conn if conn is not None else main_conn
        self._sessions[tab_id] = (terminal, effective_conn)

        # Hide broadcast button — no longer a split view
        self._tab_bar.set_broadcast_button_visible(False)
        self._tab_bar.set_broadcast_button_checked(False)
        self._tab_bar._update_broadcast_btn_style(False)

        # Unfreeze and refresh after layout settles
        QTimer.singleShot(150, lambda t=terminal, c=effective_conn: self._refresh_unwrapped(t, c))

    @staticmethod
    def _refresh_unwrapped(terminal: TerminalWidget, conn: AbstractConnection | None) -> None:
        """Unfreeze and refresh a terminal after unwrapping from SplitContainer."""
        terminal._freeze_resize = False
        terminal._recompute_size()
        terminal.update()
        if conn and hasattr(conn, 'resize'):
            conn.resize(terminal._cols, terminal._rows)

    async def _connect_split_async(
        self, conn: SSHConnection, host: Host,
    ) -> None:
        """Asynchronously connect a split panel."""
        try:
            await conn.connect()
            logger.info("Split panel connected to %s", host.address)
        except Exception as exc:
            logger.error("Split panel connection to %s failed: %s", host.address, exc)

    def toggle_broadcast(self) -> None:
        """Toggle broadcast mode on the active tab's split container."""
        active = self._tab_bar.active_tab
        if not active or active not in self._sessions:
            return
        widget, _ = self._sessions[active]
        if isinstance(widget, SplitContainer):
            new_state = not widget.broadcast_mode
            widget.set_broadcast(new_state)
            self._tab_bar.set_broadcast_button_checked(new_state)
            self._tab_bar._update_broadcast_btn_style(new_state)
        else:
            from termplus.ui.widgets.toast import ToastManager
            ToastManager.instance().show_toast(
                "Split the terminal first to use Broadcast Mode.",
                toast_type="info",
            )

    def _on_broadcast_btn_toggled(self, checked: bool) -> None:
        """Handle broadcast button click from tab bar."""
        active = self._tab_bar.active_tab
        if not active or active not in self._sessions:
            return
        widget, _ = self._sessions[active]
        if isinstance(widget, SplitContainer):
            widget.set_broadcast(checked)
            self._tab_bar._update_broadcast_btn_style(checked)

    def _on_broadcast_state_changed(self, enabled: bool) -> None:
        """Handle broadcast state change from SplitContainer (e.g. auto-off on panel close)."""
        self._tab_bar.set_broadcast_button_checked(enabled)
        self._tab_bar._update_broadcast_btn_style(enabled)

    @staticmethod
    def _freeze_all_terminals(widget: QWidget, freeze: bool) -> None:
        """Freeze or unfreeze resize on all terminals within a widget."""
        if isinstance(widget, SplitContainer):
            for panel in widget.panels:
                panel.terminal._freeze_resize = freeze
        elif hasattr(widget, '_freeze_resize'):
            widget._freeze_resize = freeze

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
        # Split view — send to the focused panel
        if isinstance(widget, SplitContainer):
            panel = widget.focused_panel
            if panel and panel.connection:
                panel.connection.send(script.encode("utf-8") + b"\n")
                return True
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

    # ------------------------------------------------------------------
    # Drag-to-split (tab dropped onto terminal area)
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        """Intercept drag events on the terminal stack to show drop zone overlay."""
        if obj is not self._terminal_stack:
            return super().eventFilter(obj, event)

        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.DragEnter:
            if event.mimeData().hasFormat(_TAB_MIME):
                # Only show overlay when there's an active SSH session
                active = self._tab_bar.active_tab
                if active and active in self._sessions:
                    _, conn = self._sessions[active]
                    if conn is not None and conn.protocol == "ssh":
                        self._drop_overlay.setGeometry(self._terminal_stack.rect())
                        self._drop_overlay.setVisible(True)
                        self._drop_overlay.raise_()
                        event.acceptProposedAction()
                        return True
        elif event.type() == QEvent.Type.Resize:
            self._drop_overlay.setGeometry(self._terminal_stack.rect())

        return super().eventFilter(obj, event)

    def _on_drop_zone_split(self, zone: str) -> None:
        """Handle a tab dropped onto a split zone in the terminal area."""
        orientation = (
            Qt.Orientation.Horizontal if zone in ("left", "right")
            else Qt.Orientation.Vertical
        )
        self._show_split_picker(orientation)

    def close_all(self) -> None:
        """Close all connections (docked and detached)."""
        for tab_id, win in list(self._detached_windows.items()):
            win.close_for_dock()
            self._detached_windows.pop(tab_id, None)
        for tab_id in list(self._sessions):
            self._on_tab_close(tab_id)
