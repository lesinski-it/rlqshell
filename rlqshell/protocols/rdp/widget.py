"""RDP display widget — hosts an embedded FreeRDP window.

Acts as a parent container: FreeRDP draws the remote desktop into a child
native window we own (passed via /parent-window:<HWND>). All keyboard, mouse
and device events are handled by FreeRDP directly. We only paint a status
overlay (connecting / error) on top.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPaintEvent
from PySide6.QtWidgets import QPushButton, QSizePolicy, QWidget

from rlqshell.protocols.rdp.connection import RDPConnection

logger = logging.getLogger(__name__)


class RDPWidget(QWidget):
    """Hosts the embedded FreeRDP child window and shows status overlays."""

    reconnect_requested = Signal()

    def __init__(
        self,
        connection: RDPConnection | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        # FreeRDP needs a real OS window handle as parent — without
        # WA_NativeWindow Qt may give the widget an alien (parent-shared)
        # window and winId() will be useless.
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        # Without our own paintEvent supplying content, the layout has nothing
        # to size against — claim the whole stretch so the embedded FreeRDP
        # window is not reduced to a thin strip.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(640, 480)

        self._conn: RDPConnection | None = None
        self._overlay_text: str | None = None
        self._overlay_color = QColor("#a6adc8")
        self._bg_color = QColor("#1e1e2e")
        self._reconnect_btn: QPushButton | None = None

        if connection is not None:
            self.set_connection(connection)

    def sizeHint(self) -> QSize:  # noqa: N802 -- Qt API
        return QSize(1280, 720)

    def set_connection(self, conn: RDPConnection) -> None:
        """Attach a connection and forward our window handle for embedding."""
        self._conn = conn
        # winId() only returns a meaningful HWND once the widget has been
        # realized. WA_NativeWindow lets us force creation right now even if
        # the widget hasn't been shown yet; we re-sync in showEvent for the
        # case where Qt assigned a different window after first realization.
        self._sync_parent_window()

    def _sync_parent_window(self) -> None:
        if self._conn is None:
            return
        try:
            wid = int(self.winId())
            self._conn.set_parent_window(wid)
            logger.debug("RDP parent window HWND = %s", wid)
        except Exception:
            logger.exception("Could not pass parent window handle to RDPConnection")

    def showEvent(self, event) -> None:  # noqa: N802 -- Qt API
        super().showEvent(event)
        # Re-grab winId now that the widget tree is fully realized; the
        # value at __init__ time can become stale once the widget joins a
        # layout/stack.
        self._sync_parent_window()

    # ------------------------------------------------------------------
    # Overlay (status / error messages)
    # ------------------------------------------------------------------

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
        fm = QFontMetricsF(QFont("JetBrains Mono", 14))
        text_height = fm.height()
        overlay_bottom = (self.height() + text_height) / 2 + 12
        bw, bh = btn.width(), btn.height()
        bx = int((self.width() - bw) / 2)
        by = min(int(overlay_bottom + 14), max(0, self.height() - bh - 8))
        btn.move(bx, by)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._reconnect_btn is not None and self._reconnect_btn.isVisible():
            self._position_reconnect_btn()

    # ------------------------------------------------------------------
    # Painting (only the overlay — FreeRDP draws the remote desktop itself)
    # ------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), self._bg_color)
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
        painter.setBrush(QColor(30, 30, 46, 220))
        painter.drawRoundedRect(QRectF(rx, ry, tw + px * 2, th + py * 2), 8, 8)
        painter.setPen(self._overlay_color)
        painter.drawText(
            QRectF(0, 0, self.width(), self.height()),
            Qt.AlignmentFlag.AlignCenter,
            self._overlay_text,
        )
