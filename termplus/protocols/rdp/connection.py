"""RDP connection — pure Python client via aardwolf library."""

from __future__ import annotations

import asyncio
import logging
import threading
from io import BytesIO

from PySide6.QtCore import Signal
from PySide6.QtGui import QImage

from termplus.protocols.base import AbstractConnection

logger = logging.getLogger(__name__)


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
        self._reader_thread: threading.Thread | None = None

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

        self.title_changed.emit(f"RDP: {self._hostname}")

        # Start reading desktop updates
        self._stop_event.clear()
        asyncio.ensure_future(self._read_loop())

    async def _read_loop(self) -> None:
        """Read desktop bitmap updates from aardwolf's ext_out_queue."""
        from aardwolf.commons.queuedata.constants import RDPDATATYPE

        try:
            while not self._stop_event.is_set():
                try:
                    data = await asyncio.wait_for(
                        self._rdp.ext_out_queue.get(), timeout=0.5,
                    )
                except asyncio.TimeoutError:
                    continue

                if data is None:
                    break

                if data.type == RDPDATATYPE.VIDEO:
                    self._emit_frame()

        except Exception as exc:
            if not self._stop_event.is_set():
                logger.error("RDP read loop error: %s", exc)
                self.error.emit(str(exc))
        finally:
            self._connected = False
            self.disconnected.emit()

    def _emit_frame(self) -> None:
        """Convert aardwolf desktop buffer to QImage and emit."""
        if not self._rdp:
            return
        try:
            from aardwolf.commons.queuedata.constants import VIDEO_FORMAT

            pil_image = self._rdp.get_desktop_buffer(VIDEO_FORMAT.PIL)
            if pil_image is None:
                return

            # Convert PIL Image -> QImage via raw RGBA bytes
            rgba = pil_image.convert("RGBA")
            data = rgba.tobytes("raw", "BGRA")
            qimg = QImage(
                data, rgba.width, rgba.height,
                rgba.width * 4, QImage.Format.Format_RGB32,
            )
            # Must copy because data buffer is temporary
            self.frame_updated.emit(qimg.copy())
        except Exception:
            logger.debug("Frame conversion error", exc_info=True)

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
        logger.info("RDP connection closed (%s)", self._hostname)
