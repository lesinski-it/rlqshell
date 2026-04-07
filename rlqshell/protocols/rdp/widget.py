"""RDP display widget — renders framebuffer and forwards keyboard/mouse."""

from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import QRect, QRectF, Qt, Slot
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from rlqshell.protocols.rdp.connection import RDPConnection

logger = logging.getLogger(__name__)


# Qt Key → RDP scancode mapping
_QT_TO_SCANCODE: dict[int, tuple[int, bool]] = {
    # (scancode, extended)
    Qt.Key.Key_Escape: (0x01, False),
    Qt.Key.Key_Tab: (0x0F, False),
    Qt.Key.Key_Backspace: (0x0E, False),
    Qt.Key.Key_Return: (0x1C, False),
    Qt.Key.Key_Enter: (0x1C, True),
    Qt.Key.Key_Insert: (0x52, True),
    Qt.Key.Key_Delete: (0x53, True),
    Qt.Key.Key_Home: (0x47, True),
    Qt.Key.Key_End: (0x4F, True),
    Qt.Key.Key_PageUp: (0x49, True),
    Qt.Key.Key_PageDown: (0x51, True),
    Qt.Key.Key_Left: (0x4B, True),
    Qt.Key.Key_Right: (0x4D, True),
    Qt.Key.Key_Up: (0x48, True),
    Qt.Key.Key_Down: (0x50, True),
    Qt.Key.Key_Shift: (0x2A, False),
    Qt.Key.Key_Control: (0x1D, False),
    Qt.Key.Key_Alt: (0x38, False),
    Qt.Key.Key_CapsLock: (0x3A, False),
    Qt.Key.Key_NumLock: (0x45, False),
    Qt.Key.Key_ScrollLock: (0x46, False),
    Qt.Key.Key_F1: (0x3B, False),
    Qt.Key.Key_F2: (0x3C, False),
    Qt.Key.Key_F3: (0x3D, False),
    Qt.Key.Key_F4: (0x3E, False),
    Qt.Key.Key_F5: (0x3F, False),
    Qt.Key.Key_F6: (0x40, False),
    Qt.Key.Key_F7: (0x41, False),
    Qt.Key.Key_F8: (0x42, False),
    Qt.Key.Key_F9: (0x43, False),
    Qt.Key.Key_F10: (0x44, False),
    Qt.Key.Key_F11: (0x57, False),
    Qt.Key.Key_F12: (0x58, False),
    Qt.Key.Key_Space: (0x39, False),
    Qt.Key.Key_Print: (0x37, True),
    Qt.Key.Key_Pause: (0x45, False),
    Qt.Key.Key_Meta: (0x5B, True),
    Qt.Key.Key_Menu: (0x5D, True),
}


class RDPWidget(QWidget):
    """Widget that displays an RDP framebuffer and forwards input events."""

    def __init__(
        self,
        connection: RDPConnection | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMouseTracking(True)

        self._conn: RDPConnection | None = connection
        self._image: QImage | None = None

        # Overlay (status / error messages)
        self._overlay_text: str | None = None
        self._overlay_color = QColor("#a6adc8")
        self._bg_color = QColor("#1e1e2e")

        if connection is not None:
            connection.frame_updated.connect(self._on_frame)

    def set_connection(self, conn: RDPConnection) -> None:
        """Attach connection after creation (used when widget must exist before connect)."""
        self._conn = conn
        conn.frame_updated.connect(self._on_frame)

    # ------------------------------------------------------------------
    # Public API (same interface as TerminalWidget / VNCWidget)
    # ------------------------------------------------------------------

    def show_overlay(self, text: str, color: str | None = None) -> None:
        self._overlay_text = text
        self._overlay_color = QColor(color) if color else QColor("#a6adc8")
        self.update()

    def clear_overlay(self) -> None:
        if self._overlay_text is not None:
            self._overlay_text = None
            self.update()

    # ------------------------------------------------------------------
    # Frame handling
    # ------------------------------------------------------------------

    @Slot(QImage)
    def _on_frame(self, image: QImage) -> None:
        self._image = image
        self.update()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), self._bg_color)

            if self._image and not self._image.isNull():
                dest = self._display_rect()
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                painter.drawImage(dest, self._image)

            if self._overlay_text:
                self._paint_overlay(painter)
        finally:
            painter.end()

    def _paint_overlay(self, painter: QPainter) -> None:
        font = QFont("JetBrains Mono", 14)
        painter.setFont(font)
        fm = QFontMetricsF(font)
        tw = fm.horizontalAdvance(self._overlay_text)
        th = fm.height()
        px, py = 24, 12
        rx = (self.width() - tw) / 2 - px
        ry = (self.height() - th) / 2 - py
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(30, 30, 46, 200))
        painter.drawRoundedRect(
            QRectF(rx, ry, tw + px * 2, th + py * 2), 8, 8,
        )
        painter.setPen(self._overlay_color)
        painter.drawText(
            QRectF(0, 0, self.width(), self.height()),
            Qt.AlignmentFlag.AlignCenter,
            self._overlay_text,
        )

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def _display_rect(self) -> QRect:
        """Image destination rectangle (centered, aspect-ratio preserved)."""
        if not self._image:
            return QRect()
        iw, ih = self._image.width(), self._image.height()
        ww, wh = self.width(), self.height()
        scale = min(ww / iw, wh / ih)
        dw, dh = int(iw * scale), int(ih * scale)
        return QRect((ww - dw) // 2, (wh - dh) // 2, dw, dh)

    def _widget_to_fb(self, pos) -> tuple[int, int]:
        """Map widget pixel position → framebuffer coordinates."""
        rect = self._display_rect()
        if rect.isEmpty() or not self._image:
            return 0, 0
        x = int((pos.x() - rect.x()) * self._image.width() / rect.width())
        y = int((pos.y() - rect.y()) * self._image.height() / rect.height())
        return (
            max(0, min(x, self._image.width() - 1)),
            max(0, min(y, self._image.height() - 1)),
        )

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        self._send_key(event, pressed=True)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        self._send_key(event, pressed=False)

    def _send_key(self, event: QKeyEvent, pressed: bool) -> None:
        if not self._conn or not self._conn.is_connected:
            return
        key = event.key()
        scancode_info = _QT_TO_SCANCODE.get(key)
        if scancode_info:
            sc, extended = scancode_info
        else:
            sc = event.nativeScanCode()
            if sc == 0:
                return
            # On Windows, native scan codes are usable directly
            extended = False

        try:
            loop = asyncio.get_event_loop()
            asyncio.ensure_future(
                self._conn._send_key_scancode(sc, pressed, extended),
            )
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Mouse
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._send_mouse_event(event, pressed=True)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._send_mouse_event(event, pressed=False)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._send_mouse_hover(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if not self._conn or not self._conn.is_connected:
            return
        from aardwolf.commons.queuedata.constants import MOUSEBUTTON
        x, y = self._widget_to_fb(event.position())
        delta = event.angleDelta().y()
        if delta > 0:
            btn = MOUSEBUTTON.MOUSEBUTTON_WHEEL_UP
        elif delta < 0:
            btn = MOUSEBUTTON.MOUSEBUTTON_WHEEL_DOWN
        else:
            return
        try:
            asyncio.ensure_future(
                self._conn._send_mouse(btn, x, y, True, abs(delta) // 120),
            )
        except RuntimeError:
            pass

    def _send_mouse_event(self, event: QMouseEvent, pressed: bool) -> None:
        if not self._conn or not self._conn.is_connected:
            return
        from aardwolf.commons.queuedata.constants import MOUSEBUTTON
        x, y = self._widget_to_fb(event.position())
        btn_map = {
            Qt.MouseButton.LeftButton: MOUSEBUTTON.MOUSEBUTTON_LEFT,
            Qt.MouseButton.RightButton: MOUSEBUTTON.MOUSEBUTTON_RIGHT,
            Qt.MouseButton.MiddleButton: MOUSEBUTTON.MOUSEBUTTON_MIDDLE,
        }
        btn = btn_map.get(event.button())
        if btn is None:
            return
        try:
            asyncio.ensure_future(
                self._conn._send_mouse(btn, x, y, pressed),
            )
        except RuntimeError:
            pass

    def _send_mouse_hover(self, event: QMouseEvent) -> None:
        if not self._conn or not self._conn.is_connected:
            return
        from aardwolf.commons.queuedata.constants import MOUSEBUTTON
        x, y = self._widget_to_fb(event.position())
        try:
            asyncio.ensure_future(
                self._conn._send_mouse(MOUSEBUTTON.MOUSEBUTTON_HOVER, x, y, False),
            )
        except RuntimeError:
            pass
