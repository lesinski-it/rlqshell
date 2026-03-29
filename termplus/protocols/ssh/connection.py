"""SSH connection using paramiko with asyncio bridge."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import threading
from typing import Callable

import paramiko

from termplus.protocols.base import AbstractConnection

logger = logging.getLogger(__name__)

# Read buffer size
_BUFSIZE = 65536


class HostKeyVerifyCallback:
    """Thread-safe callback for host key verification.

    The SSH connection is established in a background thread, but the UI dialog
    must run on the main thread. This class bridges the two using a threading
    Event to block the background thread while the main thread decides.
    """

    def __init__(self, verify_fn: Callable[[str, int, str, str], bool] | None = None):
        self._verify_fn = verify_fn

    def verify(self, hostname: str, port: int, key_type: str, fingerprint: str) -> bool:
        if self._verify_fn is None:
            return True  # auto-accept if no callback
        return self._verify_fn(hostname, port, key_type, fingerprint)


class _InteractiveHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    """Custom paramiko policy that delegates verification to a callback."""

    def __init__(self, callback: HostKeyVerifyCallback, hostname: str, port: int):
        self._callback = callback
        self._hostname = hostname
        self._port = port

    def missing_host_key(self, client, hostname, key):
        key_type = key.get_name()
        raw = key.asbytes()
        fingerprint = "SHA256:" + base64.b64encode(
            hashlib.sha256(raw).digest()
        ).rstrip(b"=").decode("ascii")

        if not self._callback.verify(self._hostname, self._port, key_type, fingerprint):
            raise paramiko.SSHException(
                f"Host key verification rejected for {self._hostname}:{self._port}"
            )


class SSHConnection(AbstractConnection):
    """Paramiko-based SSH connection running I/O in a background thread."""

    def __init__(
        self,
        hostname: str,
        port: int = 22,
        username: str = "",
        password: str | None = None,
        pkey: paramiko.PKey | None = None,
        passphrase: str | None = None,
        keep_alive: int = 60,
        agent_forwarding: bool = False,
        compression: bool = False,
        cols: int = 80,
        rows: int = 24,
        host_key_callback: HostKeyVerifyCallback | None = None,
        open_shell: bool = True,
    ) -> None:
        super().__init__()
        self._hostname = hostname
        self._port = port
        self._username = username
        self._password = password
        self._pkey = pkey
        self._passphrase = passphrase
        self._keep_alive = keep_alive
        self._agent_forwarding = agent_forwarding
        self._compression = compression
        self._cols = cols
        self._rows = rows
        self._host_key_callback = host_key_callback
        self._open_shell = open_shell

        self._client: paramiko.SSHClient | None = None
        self._channel: paramiko.Channel | None = None
        self._transport: paramiko.Transport | None = None
        self._connected = False
        self._read_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def hostname(self) -> str:
        return self._hostname

    @property
    def transport(self) -> paramiko.Transport | None:
        """Expose transport for SFTP reuse."""
        return self._transport

    async def connect(self) -> None:
        """Establish SSH connection in a thread."""
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._do_connect)
            self.connected.emit()
        except Exception as exc:
            logger.exception("SSH connection failed: %s", exc)
            self.error.emit(str(exc))
            raise

    def _do_connect(self) -> None:
        """Blocking connect (runs in thread pool)."""
        # Handle "host:port" in the hostname field
        if ":" in self._hostname:
            parts = self._hostname.rsplit(":", 1)
            if parts[1].isdigit():
                self._hostname = parts[0]
                self._port = int(parts[1])

        client = paramiko.SSHClient()
        if self._host_key_callback:
            policy = _InteractiveHostKeyPolicy(
                self._host_key_callback, self._hostname, self._port,
            )
            client.set_missing_host_key_policy(policy)
        else:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: dict = {
            "hostname": self._hostname,
            "port": self._port,
            "username": self._username,
            "timeout": 15,
            "compress": self._compression,
            "allow_agent": True,
            "look_for_keys": True,
        }
        if self._password:
            connect_kwargs["password"] = self._password
        if self._pkey:
            connect_kwargs["pkey"] = self._pkey
        if self._passphrase and not self._pkey:
            connect_kwargs["passphrase"] = self._passphrase

        client.connect(**connect_kwargs)

        self._transport = client.get_transport()
        if self._transport and self._keep_alive > 0:
            self._transport.set_keepalive(self._keep_alive)

        self._client = client
        self._connected = True

        if self._open_shell:
            channel = client.invoke_shell(
                term="xterm-256color",
                width=self._cols,
                height=self._rows,
            )
            channel.settimeout(0.1)
            self._channel = channel

            # Start reading in a background thread
            self._stop_event.clear()
            self._read_thread = threading.Thread(
                target=self._read_loop, daemon=True, name="ssh-reader"
            )
            self._read_thread.start()

        logger.info(
            "SSH connected to %s@%s:%d", self._username, self._hostname, self._port
        )

    def _read_loop(self) -> None:
        """Background thread: reads from SSH channel and emits data_received."""
        while not self._stop_event.is_set():
            if self._channel is None:
                break
            try:
                if self._channel.recv_ready():
                    data = self._channel.recv(_BUFSIZE)
                    if not data:
                        break
                    self.data_received.emit(data)
                elif self._channel.closed or self._channel.exit_status_ready():
                    break
                else:
                    self._stop_event.wait(0.01)
            except OSError:
                break
            except Exception:
                logger.exception("Error in SSH read loop")
                break

        self._connected = False
        self.disconnected.emit()

    def send(self, data: bytes) -> None:
        """Send data to the SSH channel."""
        if self._channel and not self._channel.closed:
            try:
                self._channel.sendall(data)
            except OSError:
                logger.warning("Failed to send — channel closed")
                self.close()

    def resize(self, cols: int, rows: int) -> None:
        """Resize the PTY."""
        self._cols = cols
        self._rows = rows
        if self._channel and not self._channel.closed:
            try:
                self._channel.resize_pty(width=cols, height=rows)
            except OSError:
                pass

    def close(self) -> None:
        """Close the SSH connection."""
        self._stop_event.set()
        self._connected = False

        if self._channel:
            try:
                self._channel.close()
            except Exception:
                pass
            self._channel = None

        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

        self._transport = None
        logger.info("SSH connection closed (%s)", self._hostname)
