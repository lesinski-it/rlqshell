"""SSH tunnel engine — manages local/remote port forwarding tunnels."""

from __future__ import annotations

import asyncio
import getpass
import logging
import socket
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from PySide6.QtCore import QObject, Signal

from termplus.core.credential_store import CredentialStore
from termplus.core.host_manager import HostManager
from termplus.core.keychain import Keychain
from termplus.core.models.host import Host
from termplus.core.port_forward_manager import PortForwardRule
from termplus.protocols.ssh.connection import SSHConnection

logger = logging.getLogger(__name__)

_BUFSIZE = 65536


class TunnelState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    ACTIVE = "active"
    ERROR = "error"
    STOPPING = "stopping"


@dataclass
class TunnelInfo:
    rule_id: int
    state: TunnelState = TunnelState.STOPPED
    error_message: str | None = None
    active_channels: int = 0
    started_at: datetime | None = None


@dataclass
class _TunnelContext:
    """Internal bookkeeping for a running tunnel."""

    rule: PortForwardRule
    info: TunnelInfo
    stop_event: threading.Event = field(default_factory=threading.Event)
    listen_socket: socket.socket | None = None
    ssh_conn: SSHConnection | None = None
    owns_conn: bool = True
    threads: list[threading.Thread] = field(default_factory=list)


class TunnelEngine(QObject):
    """Manages SSH tunnel lifecycle — start, stop, monitor."""

    tunnel_state_changed = Signal(int, str)  # rule_id, state string
    tunnel_error = Signal(int, str)          # rule_id, error message

    def __init__(
        self,
        host_manager: HostManager,
        credential_store: CredentialStore,
        keychain: Keychain,
    ) -> None:
        super().__init__()
        self._host_manager = host_manager
        self._credential_store = credential_store
        self._keychain = keychain

        # rule_id -> _TunnelContext
        self._tunnels: dict[int, _TunnelContext] = {}

        # Per-host SSH connection sharing: host_id -> (SSHConnection, ref_count)
        self._host_connections: dict[int, tuple[SSHConnection, int]] = {}

        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_tunnel(self, rule: PortForwardRule) -> None:
        """Start a tunnel for the given rule (async)."""
        if rule.id is None:
            return
        if self.is_running(rule.id):
            return

        if rule.direction == "dynamic":
            self._set_error(rule.id, "SOCKS5 dynamic forwarding is not yet supported.")
            return

        info = TunnelInfo(rule_id=rule.id, state=TunnelState.STARTING)
        ctx = _TunnelContext(rule=rule, info=info)
        with self._lock:
            self._tunnels[rule.id] = ctx

        self._emit_state(rule.id, TunnelState.STARTING)
        asyncio.ensure_future(self._start_tunnel_async(ctx))

    def stop_tunnel(self, rule_id: int) -> None:
        """Stop a running tunnel."""
        with self._lock:
            ctx = self._tunnels.get(rule_id)
        if ctx is None:
            return
        self._shutdown_tunnel(ctx)

    def stop_all(self) -> None:
        """Stop all running tunnels."""
        with self._lock:
            contexts = list(self._tunnels.values())
        for ctx in contexts:
            self._shutdown_tunnel(ctx)

    def is_running(self, rule_id: int) -> bool:
        with self._lock:
            ctx = self._tunnels.get(rule_id)
        if ctx is None:
            return False
        return ctx.info.state in (TunnelState.STARTING, TunnelState.ACTIVE)

    def get_tunnel_info(self, rule_id: int) -> TunnelInfo | None:
        with self._lock:
            ctx = self._tunnels.get(rule_id)
        return ctx.info if ctx else None

    def active_count(self) -> int:
        with self._lock:
            return sum(
                1 for ctx in self._tunnels.values()
                if ctx.info.state == TunnelState.ACTIVE
            )

    # ------------------------------------------------------------------
    # Async startup
    # ------------------------------------------------------------------

    async def _start_tunnel_async(self, ctx: _TunnelContext) -> None:
        rule = ctx.rule
        try:
            host = self._host_manager.get_host(rule.host_id)
            if host is None:
                self._set_error(rule.id, f"Host {rule.host_id} not found.")
                return

            conn = await self._get_or_create_connection(host)
            ctx.ssh_conn = conn

            if conn.transport is None or not conn.transport.is_active():
                self._set_error(rule.id, "SSH transport is not active.")
                return

            if rule.direction == "local":
                self._start_local_forward(ctx)
            elif rule.direction == "remote":
                self._start_remote_forward(ctx)
            else:
                self._set_error(rule.id, f"Unsupported direction: {rule.direction}")

        except Exception as exc:
            logger.exception("Failed to start tunnel for rule %s", rule.id)
            self._set_error(rule.id, str(exc))

    # ------------------------------------------------------------------
    # Local forwarding
    # ------------------------------------------------------------------

    def _start_local_forward(self, ctx: _TunnelContext) -> None:
        rule = ctx.rule
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((rule.bind_address, rule.local_port))
            sock.listen(5)
            sock.settimeout(1.0)
            ctx.listen_socket = sock
        except OSError as exc:
            self._set_error(rule.id, f"Cannot bind {rule.bind_address}:{rule.local_port} — {exc}")
            return

        ctx.info.state = TunnelState.ACTIVE
        ctx.info.started_at = datetime.now()
        self._emit_state(rule.id, TunnelState.ACTIVE)

        t = threading.Thread(
            target=self._local_accept_loop,
            args=(ctx,),
            daemon=True,
            name=f"tunnel-local-{rule.id}",
        )
        ctx.threads.append(t)
        t.start()

    def _local_accept_loop(self, ctx: _TunnelContext) -> None:
        rule = ctx.rule
        sock = ctx.listen_socket
        while not ctx.stop_event.is_set():
            try:
                client, addr = sock.accept()
            except socket.timeout:
                # Check if SSH transport is still alive
                if ctx.ssh_conn and ctx.ssh_conn.transport:
                    if not ctx.ssh_conn.transport.is_active():
                        self._set_error(rule.id, "SSH connection lost.")
                        break
                continue
            except OSError:
                if not ctx.stop_event.is_set():
                    self._set_error(rule.id, "Listen socket closed unexpectedly.")
                break

            try:
                transport = ctx.ssh_conn.transport
                channel = transport.open_channel(
                    "direct-tcpip",
                    (rule.remote_host, rule.remote_port),
                    addr,
                )
            except Exception as exc:
                logger.warning("Failed to open channel for rule %s: %s", rule.id, exc)
                client.close()
                continue

            ctx.info.active_channels += 1
            t = threading.Thread(
                target=self._forward_data,
                args=(ctx, client, channel),
                daemon=True,
                name=f"tunnel-fwd-{rule.id}",
            )
            ctx.threads.append(t)
            t.start()

    # ------------------------------------------------------------------
    # Remote forwarding
    # ------------------------------------------------------------------

    def _start_remote_forward(self, ctx: _TunnelContext) -> None:
        rule = ctx.rule
        try:
            transport = ctx.ssh_conn.transport
            transport.request_port_forward("", rule.remote_port)
        except Exception as exc:
            self._set_error(rule.id, f"Remote forward request failed: {exc}")
            return

        ctx.info.state = TunnelState.ACTIVE
        ctx.info.started_at = datetime.now()
        self._emit_state(rule.id, TunnelState.ACTIVE)

        t = threading.Thread(
            target=self._remote_accept_loop,
            args=(ctx,),
            daemon=True,
            name=f"tunnel-remote-{rule.id}",
        )
        ctx.threads.append(t)
        t.start()

    def _remote_accept_loop(self, ctx: _TunnelContext) -> None:
        rule = ctx.rule
        transport = ctx.ssh_conn.transport
        while not ctx.stop_event.is_set():
            channel = transport.accept(timeout=1.0)
            if channel is None:
                if not transport.is_active():
                    self._set_error(rule.id, "SSH connection lost.")
                    break
                continue

            try:
                local_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                local_sock.connect((rule.bind_address, rule.local_port))
            except OSError as exc:
                logger.warning(
                    "Cannot connect to local %s:%s for rule %s: %s",
                    rule.bind_address, rule.local_port, rule.id, exc,
                )
                channel.close()
                continue

            ctx.info.active_channels += 1
            t = threading.Thread(
                target=self._forward_data,
                args=(ctx, local_sock, channel),
                daemon=True,
                name=f"tunnel-rfwd-{rule.id}",
            )
            ctx.threads.append(t)
            t.start()

    # ------------------------------------------------------------------
    # Bidirectional data copy
    # ------------------------------------------------------------------

    def _forward_data(
        self,
        ctx: _TunnelContext,
        sock: socket.socket,
        channel,
    ) -> None:
        """Copy data bidirectionally between a socket and a paramiko channel.

        Uses two threads (one per direction) instead of select() which does
        not work with paramiko channels on Windows.
        """
        done = threading.Event()

        def _sock_to_chan() -> None:
            try:
                while not ctx.stop_event.is_set() and not done.is_set():
                    data = sock.recv(_BUFSIZE)
                    if not data:
                        break
                    channel.sendall(data)
            except Exception:
                pass
            finally:
                done.set()

        def _chan_to_sock() -> None:
            try:
                while not ctx.stop_event.is_set() and not done.is_set():
                    data = channel.recv(_BUFSIZE)
                    if not data:
                        break
                    sock.sendall(data)
            except Exception:
                pass
            finally:
                done.set()

        t1 = threading.Thread(target=_sock_to_chan, daemon=True)
        t2 = threading.Thread(target=_chan_to_sock, daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        try:
            sock.close()
        except Exception:
            pass
        try:
            channel.close()
        except Exception:
            pass
        ctx.info.active_channels = max(0, ctx.info.active_channels - 1)

    # ------------------------------------------------------------------
    # SSH connection management (per-host sharing)
    # ------------------------------------------------------------------

    async def _get_or_create_connection(self, host: Host) -> SSHConnection:
        """Get an existing tunnel connection for this host, or create a new one."""
        with self._lock:
            entry = self._host_connections.get(host.id)
            if entry:
                conn, ref = entry
                if conn.is_connected and conn.transport and conn.transport.is_active():
                    self._host_connections[host.id] = (conn, ref + 1)
                    return conn
                # Stale connection — discard
                del self._host_connections[host.id]

        conn = await self._create_ssh_connection(host)
        with self._lock:
            self._host_connections[host.id] = (conn, 1)
        return conn

    def _release_connection(self, host_id: int) -> None:
        """Decrement ref count; close if no more tunnels use it."""
        with self._lock:
            entry = self._host_connections.get(host_id)
            if entry is None:
                return
            conn, ref = entry
            ref -= 1
            if ref <= 0:
                del self._host_connections[host_id]
                try:
                    conn.close()
                except Exception:
                    pass
            else:
                self._host_connections[host_id] = (conn, ref)

    async def _create_ssh_connection(self, host: Host) -> SSHConnection:
        """Create a fresh SSH connection (no shell)."""
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

    # ------------------------------------------------------------------
    # Shutdown & state helpers
    # ------------------------------------------------------------------

    def _shutdown_tunnel(self, ctx: _TunnelContext) -> None:
        """Gracefully shut down a tunnel."""
        rule_id = ctx.rule.id
        if ctx.info.state in (TunnelState.STOPPED, TunnelState.STOPPING):
            return

        ctx.info.state = TunnelState.STOPPING
        self._emit_state(rule_id, TunnelState.STOPPING)

        ctx.stop_event.set()

        # Close listen socket to unblock accept()
        if ctx.listen_socket:
            try:
                ctx.listen_socket.close()
            except Exception:
                pass

        # Cancel remote forwarding
        if ctx.rule.direction == "remote" and ctx.ssh_conn and ctx.ssh_conn.transport:
            try:
                ctx.ssh_conn.transport.cancel_port_forward("", ctx.rule.remote_port)
            except Exception:
                pass

        # Join threads (with timeout to avoid hanging)
        for t in ctx.threads:
            t.join(timeout=2.0)

        # Release shared SSH connection
        if ctx.ssh_conn:
            self._release_connection(ctx.rule.host_id)

        ctx.info.state = TunnelState.STOPPED
        ctx.info.active_channels = 0
        ctx.info.started_at = None
        ctx.info.error_message = None
        self._emit_state(rule_id, TunnelState.STOPPED)

    def _set_error(self, rule_id: int, message: str) -> None:
        """Transition a tunnel to ERROR state."""
        with self._lock:
            ctx = self._tunnels.get(rule_id)
        if ctx:
            ctx.info.state = TunnelState.ERROR
            ctx.info.error_message = message
            ctx.stop_event.set()
            if ctx.listen_socket:
                try:
                    ctx.listen_socket.close()
                except Exception:
                    pass
            if ctx.ssh_conn:
                self._release_connection(ctx.rule.host_id)
        self._emit_state(rule_id, TunnelState.ERROR)
        self.tunnel_error.emit(rule_id, message)
        logger.warning("Tunnel %s error: %s", rule_id, message)

    def _emit_state(self, rule_id: int, state: TunnelState) -> None:
        self.tunnel_state_changed.emit(rule_id, state.value)
