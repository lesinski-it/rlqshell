"""VNC display widget — renders framebuffer and forwards keyboard/mouse."""

from __future__ import annotations

import logging

from PySide6.QtCore import QRect, QRectF, Qt, Signal, Slot
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
from PySide6.QtWidgets import QPushButton, QWidget

from rlqshell.protocols.vnc.connection import VNCConnection

logger = logging.getLogger(__name__)

# Qt Key → X11 Keysym
_QT_TO_KEYSYM: dict[int, int] = {
    Qt.Key.Key_Backspace: 0xFF08,
    Qt.Key.Key_Tab: 0xFF09,
    Qt.Key.Key_Return: 0xFF0D,
    Qt.Key.Key_Enter: 0xFF0D,
    Qt.Key.Key_Escape: 0xFF1B,
    Qt.Key.Key_Delete: 0xFFFF,
    Qt.Key.Key_Home: 0xFF50,
    Qt.Key.Key_Left: 0xFF51,
    Qt.Key.Key_Up: 0xFF52,
    Qt.Key.Key_Right: 0xFF53,
    Qt.Key.Key_Down: 0xFF54,
    Qt.Key.Key_PageUp: 0xFF55,
    Qt.Key.Key_PageDown: 0xFF56,
    Qt.Key.Key_End: 0xFF57,
    Qt.Key.Key_Insert: 0xFF63,
    Qt.Key.Key_F1: 0xFFBE,
    Qt.Key.Key_F2: 0xFFBF,
    Qt.Key.Key_F3: 0xFFC0,
    Qt.Key.Key_F4: 0xFFC1,
    Qt.Key.Key_F5: 0xFFC2,
    Qt.Key.Key_F6: 0xFFC3,
    Qt.Key.Key_F7: 0xFFC4,
    Qt.Key.Key_F8: 0xFFC5,
    Qt.Key.Key_F9: 0xFFC6,
    Qt.Key.Key_F10: 0xFFC7,
    Qt.Key.Key_F11: 0xFFC8,
    Qt.Key.Key_F12: 0xFFC9,
    Qt.Key.Key_Shift: 0xFFE1,
    Qt.Key.Key_Control: 0xFFE3,
    Qt.Key.Key_Alt: 0xFFE9,
    Qt.Key.Key_AltGr: 0xFFEA,
    Qt.Key.Key_Meta: 0xFFEB,
    Qt.Key.Key_CapsLock: 0xFFE5,
    Qt.Key.Key_NumLock: 0xFF7F,
    Qt.Key.Key_ScrollLock: 0xFF14,
    Qt.Key.Key_Print: 0xFF61,
    Qt.Key.Key_Pause: 0xFF13,
    Qt.Key.Key_Menu: 0xFF67,
}


class VNCWidget(QWidget):
    """Widget that displays a VNC framebuffer and forwards input events."""

    reconnect_requested = Signal()

    def __init__(
        self,
        connection: VNCConnection,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMouseTracking(True)

        self._conn = connection
        self._image: QImage | None = None
        self._button_mask = 0

        # Overlay (status / error messages)
        self._overlay_text: str | None = None
        self._overlay_color = QColor("#a6adc8")
        self._bg_color = QColor("#1e1e2e")
        self._reconnect_btn: QPushButton | None = None

        connection.frame_updated.connect(self._on_frame)

    # ------------------------------------------------------------------
    # Public API (same interface as TerminalWidget for overlay)
    # ------------------------------------------------------------------

    def set_connection(self, connection: VNCConnection) -> None:
        """Swap the underlying VNC connection (used by reconnect)."""
        old = self._conn
        if old is not None:
            try:
                old.frame_updated.disconnect(self._on_frame)
            except (RuntimeError, TypeError):
                pass
        self._conn = connection
        connection.frame_updated.connect(self._on_frame)

    def show_overlay(
        self,
        text: str,
        color: str | None = None,
        show_reconnect: bool = False,
    ) -> None:
        self._overlay_text = text
        self._overlay_color = QColor(color) if color else QColor("#a6adc8")
        self._set_reconnect_btn_visible(show_reconnect)
        self.update()

    def clear_overlay(self) -> None:
        had_text = self._overlay_text is not None
        if had_text:
            self._overlay_text = None
        if self._reconnect_btn is not None and self._reconnect_btn.isVisible():
            self._reconnect_btn.hide()
        if had_text:
            self.update()

    def _set_reconnect_btn_visible(self, visible: bool) -> None:
        if visible:
            if self._reconnect_btn is None:
                btn = QPushButton("Reconnect", self)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                btn.setStyleSheet(
                    "QPushButton { background: #89b4fa; color: #1e1e2e; "
                    "border: none; border-radius: 6px; padding: 6px 20px; "
                    "font-size: 12px; font-weight: 600; }"
                    "QPushButton:hover { background: #b4befe; }"
                    "QPushButton:pressed { background: #74c7ec; }"
                )
                btn.clicked.connect(self.reconnect_requested.emit)
                self._reconnect_btn = btn
            self._reconnect_btn.adjustSize()
            self._position_reconnect_btn()
            self._reconnect_btn.show()
            self._reconnect_btn.raise_()
        elif self._reconnect_btn is not None:
            self._reconnect_btn.hide()

    def _position_reconnect_btn(self) -> None:
        btn = self._reconnect_btn
        if btn is None or not self._overlay_text:
            return
        font = QFont("JetBrains Mono", 14)
        fm = QFontMetricsF(font)
        text_height = fm.height()
        py = 12
        overlay_bottom = (self.height() + text_height) / 2 + py
        bw = btn.width()
        bh = btn.height()
        bx = int((self.width() - bw) / 2)
        by = int(overlay_bottom + 14)
        by = min(by, max(0, self.height() - bh - 8))
        btn.move(bx, by)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._reconnect_btn is not None and self._reconnect_btn.isVisible():
            self._position_reconnect_btn()

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
        keysym = self._key_to_keysym(event)
        if keysym:
            self._conn.send_key_event(True, keysym)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        keysym = self._key_to_keysym(event)
        if keysym:
            self._conn.send_key_event(False, keysym)

    @staticmethod
    def _key_to_keysym(event: QKeyEvent) -> int | None:
        key = event.key()
        if key in _QT_TO_KEYSYM:
            return _QT_TO_KEYSYM[key]
        text = event.text()
        if text and ord(text[0]) >= 0x20:
            return ord(text[0])
        # Handle Ctrl+letter combinations (e.g., Ctrl+A → send 'A', not control char)
        modifiers = event.modifiers()
        if (modifiers & Qt.KeyboardModifier.ControlModifier) and (Qt.Key.Key_A <= key <= Qt.Key.Key_Z):
            # Send the letter itself, not the control character
            return ord(chr(key - Qt.Key.Key_A + ord('A')))
        return None

    # ------------------------------------------------------------------
    # Mouse
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._update_buttons(event, pressed=True)
        x, y = self._widget_to_fb(event.position())
        self._conn.send_pointer_event(x, y, self._button_mask)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._update_buttons(event, pressed=False)
        x, y = self._widget_to_fb(event.position())
        self._conn.send_pointer_event(x, y, self._button_mask)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        x, y = self._widget_to_fb(event.position())
        self._conn.send_pointer_event(x, y, self._button_mask)

    def wheelEvent(self, event: QWheelEvent) -> None:
        x, y = self._widget_to_fb(event.position())
        delta = event.angleDelta().y()
        if delta > 0:
            self._conn.send_pointer_event(x, y, self._button_mask | 8)   # btn 4
            self._conn.send_pointer_event(x, y, self._button_mask)
        elif delta < 0:
            self._conn.send_pointer_event(x, y, self._button_mask | 16)  # btn 5
            self._conn.send_pointer_event(x, y, self._button_mask)

    def _update_buttons(self, event: QMouseEvent, pressed: bool) -> None:
        btn = event.button()
        bit = {
            Qt.MouseButton.LeftButton: 1,
            Qt.MouseButton.MiddleButton: 2,
            Qt.MouseButton.RightButton: 4,
        }.get(btn, 0)
        if pressed:
            self._button_mask |= bit
        else:
            self._button_mask &= ~bit
