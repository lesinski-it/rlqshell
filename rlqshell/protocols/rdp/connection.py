"""RDP connection — pure Python client via aardwolf library."""

from __future__ import annotations

import asyncio
import logging
import threading

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Signal
from PySide6.QtGui import QImage, QPainter

from rlqshell.protocols.base import AbstractConnection

logger = logging.getLogger(__name__)

# Target frame interval (~30 FPS cap)
_MIN_FRAME_INTERVAL = 1.0 / 30

# Monkey-patch aardwolf's CLIPRDR response parser once so that CF_DIB/CF_DIBV5
# payloads survive as raw bytes instead of being silently dropped. Aardwolf's
# stock from_buffer only decodes text formats and leaves dataobj=None for
# everything else — that makes bidirectional image clipboard impossible without
# this shim. Applied lazily on first import from this module.
_aardwolf_patched = False


def _patch_aardwolf_image_clipboard() -> None:
    global _aardwolf_patched
    if _aardwolf_patched:
        return
    from aardwolf.extensions.RDPECLIP.protocol.formatdataresponse import (
        CLIPRDR_FORMAT_DATA_RESPONSE,
    )
    from aardwolf.extensions.RDPECLIP.protocol.formatlist import CLIPBRD_FORMAT

    _orig_from_buffer = CLIPRDR_FORMAT_DATA_RESPONSE.from_buffer

    @staticmethod
    def _patched_from_buffer(buff, otype):
        if otype in (CLIPBRD_FORMAT.CF_DIB, CLIPBRD_FORMAT.CF_DIBV5):
            msg = CLIPRDR_FORMAT_DATA_RESPONSE()
            msg.dataobj = buff.read()
            return msg
        return _orig_from_buffer(buff, otype)

    CLIPRDR_FORMAT_DATA_RESPONSE.from_buffer = _patched_from_buffer
    _aardwolf_patched = True


class _RawBytes:
    """Tiny wrapper exposing a to_bytes() method — aardwolf calls this on
    non-text clipboard payloads in CLIPRDR_FORMAT_DATA_RESPONSE.to_bytes."""

    __slots__ = ("_data",)

    def __init__(self, data: bytes) -> None:
        self._data = data

    def to_bytes(self) -> bytes:
        return self._data


class _ClipImageData:
    """Minimal object matching the RDP_CLIPBOARD_DATA protocol for CF_DIB."""

    def __init__(self, dib_bytes: bytes) -> None:
        from aardwolf.commons.queuedata import RDPDATATYPE
        from aardwolf.extensions.RDPECLIP.protocol.formatlist import CLIPBRD_FORMAT

        self.type = RDPDATATYPE.CLIPBOARD_DATA_TXT
        self.datatype = CLIPBRD_FORMAT.CF_DIB
        self.data = _RawBytes(dib_bytes)

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, _ClipImageData)
            and self.data._data == other.data._data
        )

# ---------------------------------------------------------------------------
# User-friendly error mapping
# ---------------------------------------------------------------------------

_ERROR_MAP: list[tuple[str, str]] = [
    # Authentication / credentials
    ("logon failure", "Login failed — invalid username or password."),
    ("login failed", "Login failed — invalid username or password."),
    ("authentication", "Authentication failed — check your credentials."),
    ("access denied", "Access denied — insufficient permissions for RDP connection."),
    ("account locked", "Account has been locked — contact your administrator."),
    ("account disabled", "Account is disabled."),
    ("password expired", "Password expired — change it on the target server."),
    ("credssp", "CredSSP error — the server requires Network Level Authentication (NLA)."),
    ("ntlm", "NTLM authentication error — check username, password, and domain."),
    # Network
    ("winerror 1225", "Connection refused — the remote computer rejected the connection (port closed or RDP service disabled)."),
    ("winerror 10060", "Connection timed out — host unreachable or port blocked."),
    ("winerror 10061", "Connection refused — RDP service is not listening on this port."),
    ("winerror 10065", "No route to host — check the address and network configuration."),
    ("refused", "Connection refused — the remote computer rejected the network connection."),
    ("timed out", "Connection timed out — host unreachable or port blocked."),
    ("timeout", "Connection timed out — host unreachable or port blocked."),
    ("connection refused", "Connection refused — RDP service is not listening on this port."),
    ("connection reset", "Connection was reset by the server."),
    ("no route to host", "No route to host — check the address and network configuration."),
    ("network unreachable", "Network unreachable — check your network connection."),
    ("name or service not known", "Could not resolve hostname — check the address."),
    ("getaddrinfo failed", "Could not resolve hostname — check the address."),
    # TLS / SSL
    ("ssl", "TLS/SSL connection error — server certificate problem."),
    ("certificate", "Server certificate error — untrusted connection."),
    # Protocol
    ("negotiation", "RDP protocol negotiation error with the server."),
    ("disconnect", "Server closed the connection."),
]


def _friendly_error(exc: Exception) -> str:
    """Translate a raw exception into a user-readable message."""
    raw = str(exc).lower()
    for pattern, message in _ERROR_MAP:
        if pattern in raw:
            return message
    # Fallback — return the original message
    return str(exc)


class RDPConnection(AbstractConnection):
    """RDP connection using aardwolf (pure Python, no external tools)."""

    frame_updated = Signal(QImage)
    clipboard_text_received = Signal(str)
    clipboard_image_received = Signal(QImage)
    clipboard_ready = Signal()

    def __init__(
        self,
        hostname: str,
        port: int = 3389,
        username: str | None = None,
        password: str | None = None,
        domain: str | None = None,
        resolution: str = "1920x1080",
        color_depth: int = 32,
        audio: bool = False,
        clipboard: bool = True,
    ) -> None:
        super().__init__()
        self._hostname = hostname
        self._port = port
        self._username = username
        self._password = password
        self._domain = domain
        self._resolution = resolution
        self._color_depth = color_depth
        self._clipboard = clipboard

        self._rdp = None  # aardwolf RDPConnection
        self._connected = False
        self._stop_event = threading.Event()
        self._desktop_image: QImage | None = None
        self._mcs_channel_id: int | None = None
        self._image_hooks_installed = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def protocol(self) -> str:
        return "rdp"

    async def connect(self) -> None:
        try:
            self._validate_credentials()
            await self._do_connect()
            self._connected = True
            self.connected.emit()
        except Exception as exc:
            logger.exception("RDP connection failed: %s", exc)
            self.error.emit(_friendly_error(exc))
            raise

    def _validate_credentials(self) -> None:
        """Raise early if credentials are clearly missing."""
        if not self._username:
            raise ConnectionError("Username is missing — provide RDP login credentials.")
        if not self._password:
            raise ConnectionError("Password is missing — provide RDP login password.")

    async def _do_connect(self) -> None:
        """Establish RDP connection using aardwolf."""
        # Handle "host:port" in the hostname field
        if ":" in self._hostname:
            parts = self._hostname.rsplit(":", 1)
            if parts[1].isdigit():
                self._hostname = parts[0]
                self._port = int(parts[1])

        _patch_aardwolf_image_clipboard()

        from aardwolf.commons.iosettings import RDPIOSettings
        from aardwolf.commons.queuedata.constants import VIDEO_FORMAT
        from aardwolf.commons.target import RDPTarget
        from aardwolf.connection import RDPConnection as AardwolfRDP
        from aardwolf.extensions.RDPECLIP.channel import RDPECLIPChannel
        from asyauth.common.constants import asyauthProtocol, asyauthSecret
        from asyauth.common.credentials import UniCredential

        # Parse resolution
        if self._resolution and "x" in self._resolution:
            w, h = self._resolution.split("x")
            width, height = int(w), int(h)
        else:
            width, height = 1920, 1080

        # IO settings
        iosettings = RDPIOSettings()
        iosettings.video_width = width
        iosettings.video_height = height
        iosettings.video_bpp_min = 15
        iosettings.video_bpp_max = min(self._color_depth, 32)
        iosettings.video_out_format = VIDEO_FORMAT.PIL

        # We drive the Qt clipboard ourselves — aardwolf's pyperclip integration
        # would fight us and isn't installed as a dependency anyway.
        iosettings.clipboard_use_pyperclip = False

        if not self._clipboard:
            iosettings.channels = [
                ch for ch in iosettings.channels if ch is not RDPECLIPChannel
            ]

        # Target
        target = RDPTarget(
            ip=self._hostname,
            port=self._port,
            hostname=self._hostname,
            timeout=15,
        )
        target.unsafe_ssl = True

        # Credentials
        credential = UniCredential(
            secret=self._password or "",
            username=self._username or "",
            domain=self._domain or "",
            stype=asyauthSecret.PASSWORD,
            protocol=asyauthProtocol.NTLM,
        )

        # Connect
        self._rdp = AardwolfRDP(target, credential, iosettings)
        _, err = await self._rdp.connect()
        if err is not None:
            raise ConnectionError(f"RDP connect failed: {err}")

        # Cache the MCS channel id for direct packet sending (wheel workaround).
        # aardwolf keeps joined channels on a name-mangled attribute; we access
        # it once here so _send_wheel_event doesn't have to on every scroll.
        try:
            channels = getattr(self._rdp, "_RDPConnection__joined_channels")
            self._mcs_channel_id = channels["MCS"].channel_id
        except (AttributeError, KeyError):
            self._mcs_channel_id = None

        # Prepare desktop buffer
        self._desktop_image = QImage(width, height, QImage.Format.Format_RGB32)
        self._desktop_image.fill(0xFF000000)

        self.title_changed.emit(f"RDP: {self._hostname}")

        # Start reading desktop updates
        self._stop_event.clear()
        asyncio.ensure_future(self._read_loop())

    async def _read_loop(self) -> None:
        """Read desktop bitmap updates from aardwolf's ext_out_queue."""
        from aardwolf.commons.queuedata import RDPDATATYPE

        frame_dirty = False
        last_emit = 0.0

        try:
            while not self._stop_event.is_set():
                try:
                    data = await asyncio.wait_for(
                        self._rdp.ext_out_queue.get(), timeout=0.05,
                    )
                except asyncio.TimeoutError:
                    # Flush pending frame on idle
                    if frame_dirty:
                        self._flush_frame()
                        frame_dirty = False
                    continue

                if data is None:
                    break

                if data.type == RDPDATATYPE.VIDEO:
                    self._apply_rect(data)
                    now = asyncio.get_event_loop().time()
                    if now - last_emit >= _MIN_FRAME_INTERVAL:
                        self._flush_frame()
                        last_emit = now
                        frame_dirty = False
                    else:
                        frame_dirty = True
                elif data.type == RDPDATATYPE.CLIPBOARD_READY:
                    self._install_clipboard_image_hooks()
                    self.clipboard_ready.emit()
                elif data.type == RDPDATATYPE.CLIPBOARD_DATA_TXT:
                    if self._clipboard:
                        self.clipboard_text_received.emit(data.data)
                elif data.type == RDPDATATYPE.CLIPBOARD_NEW_DATA_AVAILABLE:
                    # Server announces new clipboard data; aardwolf auto-requests
                    # text. Images are driven by our monkey-patched handler.
                    pass

        except Exception as exc:
            if not self._stop_event.is_set():
                logger.error("RDP read loop error: %s", exc)
                self.error.emit(_friendly_error(exc))
        finally:
            self._connected = False
            self.disconnected.emit()

    def _apply_rect(self, video_data) -> None:
        """Paint a rectangle update onto the persistent desktop buffer."""
        if self._desktop_image is None:
            return
        pil_rect = video_data.data
        if pil_rect is None:
            return
        try:
            rgba = pil_rect.convert("RGBA")
            raw = rgba.tobytes("raw", "BGRA")
            rect_img = QImage(
                raw, rgba.width, rgba.height,
                rgba.width * 4, QImage.Format.Format_RGB32,
            )
            painter = QPainter(self._desktop_image)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.drawImage(video_data.x, video_data.y, rect_img)
            painter.end()
        except Exception:
            logger.debug("Rect apply error", exc_info=True)

    def _flush_frame(self) -> None:
        """Emit the current desktop buffer as a frame."""
        if self._desktop_image is not None and not self._desktop_image.isNull():
            self.frame_updated.emit(self._desktop_image.copy())

    # ------------------------------------------------------------------
    # Keyboard / Mouse input
    # ------------------------------------------------------------------

    async def _send_key_scancode(self, scancode: int, is_pressed: bool, extended: bool = False) -> None:
        if self._rdp and self._connected:
            try:
                await self._rdp.send_key_scancode(scancode, is_pressed, extended)
            except Exception:
                pass

    async def _send_mouse(self, button, x: int, y: int, is_pressed: bool, steps: int = 0) -> None:
        if not (self._rdp and self._connected):
            return
        from aardwolf.commons.queuedata.constants import MOUSEBUTTON
        # Route wheel events through our own sender — aardwolf's send_mouse has
        # a bug where WHEEL_DOWN omits PTRFLAGS.WHEEL, producing a malformed
        # packet that Windows RDP servers reject by disconnecting the session.
        if button in (MOUSEBUTTON.MOUSEBUTTON_WHEEL_UP, MOUSEBUTTON.MOUSEBUTTON_WHEEL_DOWN):
            negative = button == MOUSEBUTTON.MOUSEBUTTON_WHEEL_DOWN
            try:
                await self._send_wheel_event(x, y, steps or 1, negative)
            except Exception:
                logger.debug("Wheel event send failed", exc_info=True)
            return
        try:
            await self._rdp.send_mouse(button, x, y, is_pressed, steps)
        except Exception:
            pass

    async def _send_wheel_event(self, x: int, y: int, magnitude: int, negative: bool) -> None:
        """Send a vertical mouse wheel event directly to bypass aardwolf's buggy send_mouse.

        Per [MS-RDPBCGR] 2.2.8.1.1.3.1.1.3, every vertical wheel event must set
        PTRFLAGS_WHEEL (0x0200); PTRFLAGS_WHEEL_NEGATIVE (0x0100) is merely a
        modifier bit that indicates the rotation value is negative. aardwolf's
        send_mouse sets only WHEEL_NEGATIVE for scroll-down, so the server sees
        a packet with no WHEEL flag and (because is_pressed=True in the caller)
        PTRFLAGS_DOWN without any BUTTON flag — a protocol violation that
        causes Windows to drop the RDP session. We construct the packet here
        with the correct flag set and no stray DOWN/BUTTON bits.
        """
        if x < 0 or y < 0:
            return
        if self._mcs_channel_id is None:
            return

        from aardwolf.protocol.pdu.input.mouse import PTRFLAGS, TS_POINTER_EVENT
        from aardwolf.protocol.T128.inputeventpdu import (
            TS_INPUT_EVENT,
            TS_INPUT_PDU_DATA,
            TS_SHAREDATAHEADER,
        )
        from aardwolf.protocol.T128.security import SEC_HDR_FLAG, TS_SECURITY_HEADER
        from aardwolf.protocol.T128.share import PDUTYPE2, STREAM_TYPE

        data_hdr = TS_SHAREDATAHEADER()
        data_hdr.shareID = 0x103EA
        data_hdr.streamID = STREAM_TYPE.MED
        data_hdr.pduType2 = PDUTYPE2.INPUT

        # Encode rotation as a 9-bit signed value inside WheelRotationMask.
        # Positive: raw magnitude (0x001..0x0FF).
        # Negative: 9-bit two's complement; bit 0x0100 (WHEEL_NEGATIVE) is set.
        magnitude = max(1, min(int(magnitude), 0xFF))
        rotation = (0x200 - magnitude) & 0x1FF if negative else magnitude

        mouse = TS_POINTER_EVENT()
        mouse.pointerFlags = PTRFLAGS.WHEEL | rotation
        mouse.xPos = x
        mouse.yPos = y

        cli_input = TS_INPUT_PDU_DATA()
        cli_input.slowPathInputEvents.append(TS_INPUT_EVENT.from_input(mouse))

        sec_hdr = None
        if self._rdp.cryptolayer is not None:
            sec_hdr = TS_SECURITY_HEADER()
            sec_hdr.flags = SEC_HDR_FLAG.ENCRYPT
            sec_hdr.flagsHi = 0

        await self._rdp.handle_out_data(
            cli_input, sec_hdr, data_hdr, None, self._mcs_channel_id, False,
        )

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------

    async def send_clipboard_text(self, text: str) -> None:
        """Push a text value to the remote clipboard."""
        if not (self._rdp and self._connected and self._clipboard):
            return
        try:
            await self._rdp.set_current_clipboard_text(text)
        except Exception:
            logger.debug("send_clipboard_text failed", exc_info=True)

    async def send_clipboard_image(self, image: QImage) -> None:
        """Push a QImage to the remote clipboard as CF_DIB."""
        if not (self._rdp and self._connected and self._clipboard):
            return
        if image is None or image.isNull():
            return
        try:
            dib = self._qimage_to_dib(image)
            clip_data = _ClipImageData(dib)
            await self._rdp.iosettings.clipboard.set_data(clip_data)
        except Exception:
            logger.debug("send_clipboard_image failed", exc_info=True)

    @staticmethod
    def _qimage_to_dib(image: QImage) -> bytes:
        """QImage → CF_DIB: write BMP to memory and strip the 14-byte file header."""
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buf, "BMP")
        bmp_bytes = bytes(buf.data())
        return bmp_bytes[14:]  # drop BITMAPFILEHEADER

    @staticmethod
    def _dib_to_qimage(dib_bytes: bytes) -> QImage | None:
        """CF_DIB → QImage: synthesize the BITMAPFILEHEADER and parse as BMP."""
        if len(dib_bytes) < 40:
            return None
        # DIB header size is at the start (BITMAPINFOHEADER.biSize = 40, V5 = 124).
        header_size = int.from_bytes(dib_bytes[:4], "little")
        # Color table follows the header; data offset skips DIB header + color table.
        # For 24/32-bpp images the color table is absent (biClrUsed=0), so offset
        # == 14 + header_size. For paletted formats this is approximate; we let
        # QImage best-effort decode.
        data_offset = 14 + header_size
        file_size = 14 + len(dib_bytes)
        file_header = (
            b"BM"
            + file_size.to_bytes(4, "little")
            + b"\x00\x00\x00\x00"
            + data_offset.to_bytes(4, "little")
        )
        img = QImage()
        if img.loadFromData(QByteArray(file_header + dib_bytes), "BMP"):
            return img
        return None

    def _install_clipboard_image_hooks(self) -> None:
        """Instance-level monkey-patches on the cliprdr channel to handle
        CF_DIB/CF_DIBV5 format announcements and data responses."""
        if not self._rdp or self._image_hooks_installed:
            return
        try:
            channels = getattr(self._rdp, "_RDPConnection__joined_channels")
            cliprdr = channels.get("cliprdr")
        except AttributeError:
            cliprdr = None
        if cliprdr is None:
            return

        from aardwolf.extensions.RDPECLIP.protocol import (
            CB_TYPE,
            CLIPRDR_FORMAT_DATA_REQUEST,
            CLIPRDR_HEADER,
        )
        from aardwolf.extensions.RDPECLIP.protocol.formatlist import CLIPBRD_FORMAT

        _orig_handle_fmt_list = cliprdr._handle_format_list
        _orig_handle_fmt_data_resp = cliprdr._handle_format_data_response
        conn_ref = self  # captured for async callbacks

        async def _patched_handle_format_list(fmtl):
            await _orig_handle_fmt_list(fmtl)
            # aardwolf already auto-requests CF_UNICODETEXT. If the server also
            # advertises a bitmap format AND no text is on offer, ask for the
            # image instead. (If both are on offer we let text win — matches
            # how Windows RDP prioritizes.)
            if CLIPBRD_FORMAT.CF_UNICODETEXT in cliprdr.current_server_formats:
                return
            for img_fmt in (CLIPBRD_FORMAT.CF_DIB, CLIPBRD_FORMAT.CF_DIBV5):
                if img_fmt in cliprdr.current_server_formats:
                    # Name-mangled private attr — set the "requested" marker so
                    # the response handler parses it as an image.
                    cliprdr._RDPECLIPChannel__requested_format = img_fmt
                    dreq = CLIPRDR_FORMAT_DATA_REQUEST()
                    dreq.requestedFormatId = img_fmt
                    msg = CLIPRDR_HEADER.serialize_packet(
                        CB_TYPE.CB_FORMAT_DATA_REQUEST, 0, dreq,
                    )
                    await cliprdr.fragment_and_send(msg)
                    return

        async def _patched_handle_format_data_response(fmtdata):
            requested = getattr(
                cliprdr, "_RDPECLIPChannel__requested_format", None,
            )
            if requested in (CLIPBRD_FORMAT.CF_DIB, CLIPBRD_FORMAT.CF_DIBV5):
                try:
                    img = RDPConnection._dib_to_qimage(fmtdata.dataobj)
                    if img is not None and not img.isNull() and conn_ref._clipboard:
                        conn_ref.clipboard_image_received.emit(img)
                except Exception:
                    logger.debug("CF_DIB decode failed", exc_info=True)
                return
            await _orig_handle_fmt_data_resp(fmtdata)

        cliprdr._handle_format_list = _patched_handle_format_list
        cliprdr._handle_format_data_response = _patched_handle_format_data_response
        self._image_hooks_installed = True

    # ------------------------------------------------------------------
    # AbstractConnection interface (not used for RDP)
    # ------------------------------------------------------------------

    def send(self, data: bytes) -> None:
        pass

    def resize(self, cols: int, rows: int) -> None:
        pass

    def close(self) -> None:
        self._stop_event.set()
        self._connected = False
        if self._rdp:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(self._rdp.send_disconnect())
                else:
                    loop.run_until_complete(self._rdp.send_disconnect())
            except Exception:
                pass
            self._rdp = None
        self._desktop_image = None
        logger.info("RDP connection closed (%s)", self._hostname)
