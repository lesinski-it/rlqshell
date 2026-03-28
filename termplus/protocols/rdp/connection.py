"""RDP connection — pure Python client via aardwolf library."""

from __future__ import annotations

import asyncio
import logging
import threading

from PySide6.QtCore import Signal
from PySide6.QtGui import QImage, QPainter

from termplus.protocols.base import AbstractConnection

logger = logging.getLogger(__name__)

# Target frame interval (~30 FPS cap)
_MIN_FRAME_INTERVAL = 1.0 / 30


class RDPConnection(AbstractConnection):
    """RDP connection using aardwolf (pure Python, no external tools)."""

    frame_updated = Signal(QImage)

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

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        try:
            await self._do_connect()
            self._connected = True
            self.connected.emit()
        except Exception as exc:
            logger.exception("RDP connection failed: %s", exc)
            self.error.emit(str(exc))
            raise

    async def _do_connect(self) -> None:
        """Establish RDP connection using aardwolf."""
        # Handle "host:port" in the hostname field
        if ":" in self._hostname:
            parts = self._hostname.rsplit(":", 1)
            if parts[1].isdigit():
                self._hostname = parts[0]
                self._port = int(parts[1])

        from aardwolf.commons.iosettings import RDPIOSettings
        from aardwolf.commons.queuedata.constants import VIDEO_FORMAT
        from aardwolf.commons.target import RDPTarget
        from aardwolf.connection import RDPConnection as AardwolfRDP
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

        if not self._clipboard:
            iosettings.channels = []

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

        except Exception as exc:
            if not self._stop_event.is_set():
                logger.error("RDP read loop error: %s", exc)
                self.error.emit(str(exc))
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
        if self._rdp and self._connected:
            try:
                await self._rdp.send_mouse(button, x, y, is_pressed, steps)
            except Exception:
                pass

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
