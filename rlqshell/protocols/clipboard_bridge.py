"""Bidirectional clipboard sync between QApplication.clipboard() and a
remote RDP/VNC session."""

from __future__ import annotations

import asyncio
import hashlib
import logging

from PySide6.QtCore import QObject, Slot
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)


class ClipboardBridge(QObject):
    """Keeps QClipboard in sync with a remote session.

    Each session owns one bridge. Because QApplication.clipboard() is a
    process-wide singleton, bridges for multiple tabs naturally share clipboard
    state — copying in RDP session A routes through QClipboard and lands in
    VNC session B without any central buffer of our own.

    A fingerprint of the last value we pushed in each direction prevents
    round-trip echoes (server A → QClipboard → server A).
    """

    def __init__(self, conn, protocol: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._protocol = protocol
        self._clipboard = QApplication.clipboard()
        self._last_local_fp: bytes | None = None
        self._last_remote_fp: bytes | None = None
        self._ready = protocol == "vnc"  # VNC is ready on connect; RDP waits for CLIPRDR_READY

        # Load configuration from app config
        clipboard_enabled = True
        try:
            app = QApplication.instance()
            config = getattr(app, "config", None)
            if config:
                clipboard_enabled = config.get("clipboard.enabled", True)
                self._text_limit = config.get("clipboard.text_size_limit_kb", 500) * 1024
                self._image_limit = config.get("clipboard.image_size_limit_mb", 25) * 1024 * 1024
            else:
                self._text_limit = 500 * 1024
                self._image_limit = 25 * 1024 * 1024
        except Exception:
            self._text_limit = 500 * 1024
            self._image_limit = 25 * 1024 * 1024

        # Only connect signals if clipboard is globally enabled
        if clipboard_enabled:
            self._clipboard.dataChanged.connect(self._on_local_changed)
            conn.clipboard_text_received.connect(self._on_remote_text)

            if protocol == "rdp":
                conn.clipboard_image_received.connect(self._on_remote_image)
                conn.clipboard_ready.connect(self._on_ready)

            logger.info("ClipboardBridge created for %s session", protocol)
        else:
            logger.info("ClipboardBridge disabled for %s session (global config)", protocol)

    @Slot()
    def _on_ready(self) -> None:
        self._ready = True

    # ------------------------------------------------------------------
    # Fingerprints
    # ------------------------------------------------------------------

    @staticmethod
    def _fp_text(text: str) -> bytes:
        return hashlib.sha256(text.encode("utf-8", errors="replace")).digest()

    @staticmethod
    def _fp_image(image: QImage) -> bytes:
        if image is None or image.isNull():
            return b""
        ptr = image.constBits()
        if ptr is None:
            return b""
        try:
            raw = bytes(ptr)
        except TypeError:
            # Some PySide builds return a memoryview; fall back.
            raw = bytes(memoryview(ptr))
        h = hashlib.sha256()
        h.update(image.width().to_bytes(4, "little"))
        h.update(image.height().to_bytes(4, "little"))
        h.update(raw)
        return h.digest()

    # ------------------------------------------------------------------
    # Local → remote
    # ------------------------------------------------------------------

    @Slot()
    def _on_local_changed(self) -> None:
        if not self._ready:
            return
        mime = self._clipboard.mimeData()
        if mime is None:
            return

        if self._protocol == "rdp" and mime.hasImage():
            image = self._clipboard.image()
            if image is None or image.isNull():
                return
            # Check image size (estimate: width * height * 4 bytes per pixel)
            raw_size = image.width() * image.height() * 4
            if raw_size > self._image_limit:
                logger.warning(
                    "ClipboardBridge[rdp]: image too large (%dx%d = ~%d MB), skip",
                    image.width(), image.height(), raw_size // (1024 * 1024),
                )
                return
            fp = self._fp_image(image)
            if fp == self._last_remote_fp or fp == self._last_local_fp:
                return
            self._last_local_fp = fp
            try:
                asyncio.ensure_future(self._conn.send_clipboard_image(image))
            except RuntimeError:
                logger.debug("no running loop for send_clipboard_image")
            return

        if mime.hasText():
            text = mime.text()
            if not text:
                return
            # Check text size (encode to see actual byte length)
            text_bytes = len(text.encode("utf-8", errors="replace"))
            if text_bytes > self._text_limit:
                logger.warning(
                    "ClipboardBridge[%s]: text too large (%d bytes = ~%.1f MB), skip",
                    self._protocol, text_bytes, text_bytes / (1024 * 1024),
                )
                return
            fp = self._fp_text(text)
            if fp == self._last_remote_fp:
                logger.debug(
                    "ClipboardBridge[%s]: local text matches last remote, skip echo",
                    self._protocol,
                )
                return
            if fp == self._last_local_fp:
                return
            self._last_local_fp = fp
            logger.info(
                "ClipboardBridge[%s]: local text → remote (%d chars, preview=%r)",
                self._protocol, len(text), text[:80],
            )
            if self._protocol == "rdp":
                try:
                    asyncio.ensure_future(self._conn.send_clipboard_text(text))
                except RuntimeError:
                    logger.debug("no running loop for send_clipboard_text")
            else:  # vnc
                self._conn.send_client_cut_text(text)

    # ------------------------------------------------------------------
    # Remote → local
    # ------------------------------------------------------------------

    @Slot(str)
    def _on_remote_text(self, text: str) -> None:
        fp = self._fp_text(text)
        if fp == self._last_local_fp:
            logger.debug(
                "ClipboardBridge[%s]: remote text matches last local, skip echo",
                self._protocol,
            )
            return
        self._last_remote_fp = fp
        logger.info(
            "ClipboardBridge[%s]: remote text → QClipboard (%d chars, preview=%r)",
            self._protocol, len(text), text[:80],
        )
        self._clipboard.setText(text, mode=self._clipboard.Mode.Clipboard)

    @Slot(QImage)
    def _on_remote_image(self, image: QImage) -> None:
        if image is None or image.isNull():
            return
        fp = self._fp_image(image)
        if fp == self._last_local_fp:
            return
        self._last_remote_fp = fp
        self._clipboard.setImage(image, mode=self._clipboard.Mode.Clipboard)

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    def detach(self) -> None:
        """Disconnect all signals. Called on tab close / reconnect."""
        try:
            self._clipboard.dataChanged.disconnect(self._on_local_changed)
        except (RuntimeError, TypeError):
            pass
        for sig_name in ("clipboard_text_received", "clipboard_image_received", "clipboard_ready"):
            sig = getattr(self._conn, sig_name, None)
            if sig is None:
                continue
            try:
                sig.disconnect(self)
            except (RuntimeError, TypeError):
                pass
