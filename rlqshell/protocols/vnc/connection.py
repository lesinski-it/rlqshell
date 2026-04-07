"""VNC connection using RFB 3.8 protocol."""

from __future__ import annotations

import asyncio
import logging
import socket
import struct
import threading

from PySide6.QtCore import Signal
from PySide6.QtGui import QImage

from rlqshell.protocols.base import AbstractConnection

logger = logging.getLogger(__name__)


class VNCConnection(AbstractConnection):
    """RFB 3.8 protocol client for VNC connections."""

    frame_updated = Signal(QImage)

    def __init__(
        self,
        hostname: str,
        port: int = 5900,
        password: str | None = None,
        view_only: bool = False,
    ) -> None:
        super().__init__()
        self._hostname = hostname
        self._port = port
        self._password = password
        self._view_only = view_only

        self._sock: socket.socket | None = None
        self._connected = False
        self._stop_event = threading.Event()
        self._read_thread: threading.Thread | None = None

        self._width = 0
        self._height = 0
        self._name = ""
        self._fb_data: bytearray | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def protocol(self) -> str:
        return "vnc"

    @property
    def fb_width(self) -> int:
        return self._width

    @property
    def fb_height(self) -> int:
        return self._height

    async def connect(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._do_connect)
            self.connected.emit()
        except Exception as exc:
            logger.exception("VNC connection to %s:%d failed: %s", self._hostname, self._port, exc)
            self.error.emit(f"Connection to {self._hostname}:{self._port} failed: {exc}")
            raise

    # ------------------------------------------------------------------
    # RFB handshake
    # ------------------------------------------------------------------

    def _recv_exact(self, n: int) -> bytes:
        """Read exactly *n* bytes, respecting the stop event."""
        buf = b""
        while len(buf) < n:
            if self._stop_event.is_set():
                raise ConnectionError("Connection closing")
            try:
                chunk = self._sock.recv(n - len(buf))
                if not chunk:
                    raise ConnectionError("VNC connection closed")
                buf += chunk
            except socket.timeout:
                continue
        return buf

    def _do_connect(self) -> None:
        """Blocking RFB 3.8 handshake (runs in thread-pool)."""
        # Handle "host:port" in the hostname field
        if ":" in self._hostname:
            parts = self._hostname.rsplit(":", 1)
            if parts[1].isdigit():
                self._hostname = parts[0]
                self._port = int(parts[1])

        logger.info("VNC connecting to %s:%d", self._hostname, self._port)
        sock = socket.create_connection((self._hostname, self._port), timeout=15)
        sock.settimeout(5)
        self._sock = sock

        # 1. Protocol version
        version = self._recv_exact(12)
        if not version.startswith(b"RFB "):
            raise ConnectionError(f"Not a VNC server: {version!r}")
        logger.info("VNC server: %s", version.decode("ascii").strip())
        sock.sendall(b"RFB 003.008\n")

        # 2. Security
        num_types = struct.unpack("!B", self._recv_exact(1))[0]
        if num_types == 0:
            rlen = struct.unpack("!I", self._recv_exact(4))[0]
            reason = self._recv_exact(rlen).decode("utf-8", errors="replace")
            raise ConnectionError(f"Server refused: {reason}")

        sec_types = list(self._recv_exact(num_types))
        logger.info("Security types offered: %s", sec_types)

        if 1 in sec_types:
            sock.sendall(struct.pack("!B", 1))
        elif 2 in sec_types:
            if not self._password:
                raise ConnectionError("VNC server requires a password")
            sock.sendall(struct.pack("!B", 2))
            self._vnc_auth()
        else:
            raise ConnectionError(f"No supported security type: {sec_types}")

        # Security result
        result = struct.unpack("!I", self._recv_exact(4))[0]
        if result != 0:
            try:
                rlen = struct.unpack("!I", self._recv_exact(4))[0]
                reason = self._recv_exact(rlen).decode("utf-8", errors="replace")
            except Exception:
                reason = "Authentication failed"
            raise ConnectionError(reason)

        # 3. ClientInit — shared flag = 1
        sock.sendall(struct.pack("!B", 1))

        # 4. ServerInit
        header = self._recv_exact(24)
        self._width, self._height = struct.unpack("!HH", header[:4])
        name_len = struct.unpack("!I", header[20:24])[0]
        self._name = self._recv_exact(name_len).decode("utf-8", errors="replace")
        logger.info("Desktop: %s (%dx%d)", self._name, self._width, self._height)

        # Allocate framebuffer (Format_RGB32: 0xFFRRGGBB, LE bytes BB GG RR FF)
        self._fb_data = bytearray(self._width * self._height * 4)
        self._fb_data[3::4] = b"\xff" * (self._width * self._height)

        # Set our pixel format: 32 bpp LE, r<<16 | g<<8 | b
        pf = struct.pack(
            "!BBBBHHHBBBxxx",
            32, 24, 0, 1,        # bpp, depth, big-endian=0, true-colour=1
            255, 255, 255,       # r/g/b max
            16, 8, 0,            # r/g/b shift
        )
        sock.sendall(struct.pack("!Bxxx", 0) + pf)

        # Set encodings: CopyRect (1), Raw (0)
        encodings = [1, 0]
        msg = struct.pack("!BxH", 2, len(encodings))
        for enc in encodings:
            msg += struct.pack("!i", enc)
        sock.sendall(msg)

        # Request initial full framebuffer
        sock.sendall(struct.pack("!BBHHHH", 3, 0, 0, 0, self._width, self._height))

        self._connected = True
        sock.settimeout(0.5)

        # Start reader thread
        self._stop_event.clear()
        self._read_thread = threading.Thread(
            target=self._read_loop, daemon=True, name="vnc-reader",
        )
        self._read_thread.start()
        self.title_changed.emit(self._name)

    def _vnc_auth(self) -> None:
        """DES challenge-response authentication (security type 2)."""
        challenge = self._recv_exact(16)
        key = (self._password or "").encode("latin-1")[:8].ljust(8, b"\x00")

        # VNC reverses bits in each key byte
        def _rev(b: int) -> int:
            r = 0
            for _ in range(8):
                r = (r << 1) | (b & 1)
                b >>= 1
            return r

        des_key = bytes(_rev(b) for b in key)

        # TripleDES(K+K+K) == single DES(K)
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        cipher = Cipher(algorithms.TripleDES(des_key * 3), modes.ECB())
        enc = cipher.encryptor()
        response = enc.update(challenge[:8]) + enc.update(challenge[8:16])
        enc.finalize()
        self._sock.sendall(response)

    # ------------------------------------------------------------------
    # Read loop — runs in background thread
    # ------------------------------------------------------------------

    def _read_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                msg_type = self._recv_exact(1)[0]
                if msg_type == 0:
                    self._handle_fb_update()
                elif msg_type == 1:
                    self._handle_colour_map()
                elif msg_type == 2:
                    pass  # Bell — ignored
                elif msg_type == 3:
                    self._handle_cut_text()
                else:
                    logger.warning("Unknown VNC message type: %d", msg_type)
                    break
            except (ConnectionError, OSError):
                break
            except Exception:
                logger.exception("VNC read loop error")
                break

        self._connected = False
        self.disconnected.emit()

    # ------------------------------------------------------------------
    # Server → Client message handlers
    # ------------------------------------------------------------------

    def _handle_fb_update(self) -> None:
        header = self._recv_exact(3)
        num_rects = struct.unpack("!xH", header)[0]

        for _ in range(num_rects):
            rh = self._recv_exact(12)
            x, y, w, h, enc = struct.unpack("!HHHHi", rh)

            if enc == 0:
                self._decode_raw(x, y, w, h)
            elif enc == 1:
                src = self._recv_exact(4)
                sx, sy = struct.unpack("!HH", src)
                self._decode_copyrect(x, y, w, h, sx, sy)
            else:
                logger.warning("Unsupported VNC encoding: %d", enc)
                break

        self._emit_frame()

        # Request next incremental update
        if self._connected and self._sock:
            try:
                self._sock.sendall(
                    struct.pack("!BBHHHH", 3, 1, 0, 0, self._width, self._height)
                )
            except OSError:
                pass

    def _decode_raw(self, x: int, y: int, w: int, h: int) -> None:
        data = bytearray(self._recv_exact(w * h * 4))
        data[3::4] = b"\xff" * (w * h)  # fix alpha

        stride = self._width * 4
        for row in range(h):
            src = row * w * 4
            dst = (y + row) * stride + x * 4
            self._fb_data[dst : dst + w * 4] = data[src : src + w * 4]

    def _decode_copyrect(
        self, x: int, y: int, w: int, h: int, sx: int, sy: int,
    ) -> None:
        stride = self._width * 4
        # Copy to temp first to handle overlap
        tmp = bytearray(w * h * 4)
        for row in range(h):
            s = (sy + row) * stride + sx * 4
            tmp[row * w * 4 : (row + 1) * w * 4] = self._fb_data[s : s + w * 4]
        for row in range(h):
            d = (y + row) * stride + x * 4
            t = row * w * 4
            self._fb_data[d : d + w * 4] = tmp[t : t + w * 4]

    def _handle_colour_map(self) -> None:
        header = self._recv_exact(5)
        _, _, num = struct.unpack("!xHH", header)
        self._recv_exact(num * 6)  # discard

    def _handle_cut_text(self) -> None:
        header = self._recv_exact(7)
        length = struct.unpack("!xxxI", header)[0]
        self._recv_exact(length)  # discard

    def _emit_frame(self) -> None:
        if not self._fb_data:
            return
        img = QImage(
            bytes(self._fb_data),
            self._width,
            self._height,
            self._width * 4,
            QImage.Format.Format_RGB32,
        )
        # Must copy — the bytes buffer is temporary and QImage only holds a pointer
        self.frame_updated.emit(img.copy())

    # ------------------------------------------------------------------
    # Client → Server messages
    # ------------------------------------------------------------------

    def send_key_event(self, down: bool, keysym: int) -> None:
        if not self._connected or self._view_only or not self._sock:
            return
        try:
            self._sock.sendall(struct.pack("!BBxxI", 4, int(down), keysym))
        except OSError:
            pass

    def send_pointer_event(self, x: int, y: int, button_mask: int) -> None:
        if not self._connected or self._view_only or not self._sock:
            return
        x = max(0, min(x, self._width - 1))
        y = max(0, min(y, self._height - 1))
        try:
            self._sock.sendall(struct.pack("!BBHH", 5, button_mask, x, y))
        except OSError:
            pass

    # ------------------------------------------------------------------
    # AbstractConnection interface (unused for VNC)
    # ------------------------------------------------------------------

    def send(self, data: bytes) -> None:
        pass

    def resize(self, cols: int, rows: int) -> None:
        pass

    def close(self) -> None:
        self._stop_event.set()
        self._connected = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        logger.info("VNC connection closed (%s)", self._hostname)
