"""RDP tab widget for standalone FreeRDP sessions.

We deliberately do NOT use FreeRDP's /parent-window embedding on Windows.
FreeRDP runs as a normal top-level window while the RLQShell tab provides
status and quick actions (focus, fullscreen toggle).

Why this approach:

1. wfreerdp 3.21 / 3.25 (deprecated win32 client, what we bundle) ignores
   SetWindowPos when launched with /parent-window — the embedded child
   stays at its initial /size: and never matches the Qt widget area.
2. /smart-sizing crashes the same client during session negotiation
   (FreeRDP exits with -1002 immediately).

This keeps the session stable and avoids embedding-specific rendering bugs.
"""

from __future__ import annotations

import ctypes
import logging
import sys

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPaintEvent,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from rlqshell.protocols.rdp.connection import RDPConnection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Win32: find the xfreerdp top-level window for a known PID and bring it
# to the foreground. Used only by the "Pokaż okno RDP" button.
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32

    _EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p,
    )
    _user32.EnumWindows.argtypes = [_EnumWindowsProc, ctypes.c_void_p]
    _user32.EnumWindows.restype = ctypes.c_bool
    _user32.GetWindowThreadProcessId.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong),
    ]
    _user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
    _user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    _user32.IsWindowVisible.restype = ctypes.c_bool
    _user32.GetClassNameW.argtypes = [
        ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int,
    ]
    _user32.GetClassNameW.restype = ctypes.c_int
    _user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    _user32.SetForegroundWindow.restype = ctypes.c_bool
    _user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _user32.ShowWindow.restype = ctypes.c_bool
    _user32.IsIconic.argtypes = [ctypes.c_void_p]
    _user32.IsIconic.restype = ctypes.c_bool
    _user32.AttachThreadInput.argtypes = [
        ctypes.c_ulong, ctypes.c_ulong, ctypes.c_bool,
    ]
    _user32.AttachThreadInput.restype = ctypes.c_bool
    _kernel32.GetCurrentThreadId.restype = ctypes.c_ulong

    _SW_RESTORE = 9

    def _window_class(hwnd: int) -> str:
        buf = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(hwnd, buf, 256)
        return buf.value or ""

    def _find_toplevel_for_pid(pid: int) -> int | None:
        if not pid:
            return None
        candidates: list[int] = []

        def _cb(hwnd, _lparam):
            try:
                wnd_pid = ctypes.c_ulong(0)
                _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wnd_pid))
                if wnd_pid.value != pid:
                    return True
                if not _user32.IsWindowVisible(hwnd):
                    return True
                cls = _window_class(hwnd)
                if "freerdp" in cls.lower():
                    candidates.append(int(hwnd))
            except Exception:
                pass
            return True

        try:
            _user32.EnumWindows(_EnumWindowsProc(_cb), None)
        except Exception:
            return None
        return candidates[0] if candidates else None

    def _bring_window_to_front(hwnd: int) -> None:
        """Restore + bring to front + give keyboard focus.

        Uses AttachThreadInput so SetForegroundWindow is not silently
        denied across the process boundary.
        """
        if not hwnd:
            return
        try:
            if _user32.IsIconic(hwnd):
                _user32.ShowWindow(hwnd, _SW_RESTORE)
            target_thread = _user32.GetWindowThreadProcessId(hwnd, None)
            current_thread = _kernel32.GetCurrentThreadId()
            attached = False
            if target_thread and target_thread != current_thread:
                attached = bool(_user32.AttachThreadInput(
                    current_thread, target_thread, True,
                ))
            try:
                _user32.SetForegroundWindow(hwnd)
            finally:
                if attached:
                    _user32.AttachThreadInput(
                        current_thread, target_thread, False,
                    )
        except Exception:
            logger.debug("BringToFront failed for HWND %s", hwnd, exc_info=True)

else:
    def _find_toplevel_for_pid(pid: int) -> int | None:  # noqa: ARG001
        return None

    def _bring_window_to_front(hwnd: int) -> None:  # noqa: ARG001
        pass




# ---------------------------------------------------------------------------
# RDPWidget
# ---------------------------------------------------------------------------

class RDPWidget(QWidget):
    """Status panel for the RDP tab while FreeRDP runs in its own window."""

    reconnect_requested = Signal()

    def __init__(
        self,
        connection: RDPConnection | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(640, 320)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

        self._conn: RDPConnection | None = None
        self._overlay_text: str | None = None
        self._overlay_color = QColor("#a6adc8")
        self._bg_color = QColor("#1e1e2e")
        self._reconnect_btn: QPushButton | None = None

        # Vertical layout: top spacer -> centered "Bring window to front" button
        # -> bottom spacer. paintEvent draws background + status text.
        btn_style = (
            "QPushButton { background: #89b4fa; color: #1e1e2e; "
            "border: none; border-radius: 8px; padding: 10px 24px; "
            "font-size: 13px; font-weight: 600; }"
            "QPushButton:hover { background: #b4befe; }"
            "QPushButton:pressed { background: #74c7ec; }"
            "QPushButton:disabled { background: #45475a; color: #6c7086; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 80, 40, 80)
        layout.addStretch(2)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch(1)
        self._focus_btn = QPushButton("Pokaż okno RDP", self)
        self._focus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._focus_btn.setStyleSheet(btn_style)
        self._focus_btn.clicked.connect(self._focus_rdp_window)
        self._focus_btn.setEnabled(False)
        btn_row.addWidget(self._focus_btn)

        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        layout.addStretch(3)

        # Periodic check: enable the button once xfreerdp's window appears.
        self._discover_timer = QTimer(self)
        self._discover_timer.setInterval(500)
        self._discover_timer.timeout.connect(self._check_window_available)

        if connection is not None:
            self.set_connection(connection)

    def sizeHint(self) -> QSize:  # noqa: N802 -- Qt API
        return QSize(720, 480)

    # ------------------------------------------------------------------
    # Connection wiring
    # ------------------------------------------------------------------

    def set_connection(self, conn: RDPConnection) -> None:
        self._conn = conn
        self._focus_btn.setEnabled(False)
        if sys.platform == "win32":
            self._discover_timer.start()

    def _check_window_available(self) -> None:
        if self._conn is None or self._conn.pid is None:
            self._focus_btn.setEnabled(False)
            return
        hwnd = _find_toplevel_for_pid(self._conn.pid)
        self._focus_btn.setEnabled(hwnd is not None)
        if hwnd is None and not self._conn.is_connected:
            # xfreerdp exited; no point polling further.
            self._discover_timer.stop()

    def _focus_rdp_window(self) -> None:
        if self._conn is None or self._conn.pid is None:
            return
        hwnd = _find_toplevel_for_pid(self._conn.pid)
        if hwnd:
            _bring_window_to_front(hwnd)

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
                    "QPushButton { background: #f38ba8; color: #1e1e2e; "
                    "border: none; border-radius: 6px; padding: 6px 20px; "
                    "font-size: 12px; font-weight: 600; }"
                    "QPushButton:hover { background: #fab387; }"
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
        bw, bh = btn.width(), btn.height()
        bx = int((self.width() - bw) / 2)
        by = int(self.height() / 2 + 60)
        by = min(by, max(0, self.height() - bh - 8))
        btn.move(bx, by)

    def resizeEvent(self, event) -> None:  # noqa: N802 -- Qt API
        super().resizeEvent(event)
        if self._reconnect_btn is not None and self._reconnect_btn.isVisible():
            self._position_reconnect_btn()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 -- Qt API
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), self._bg_color)
            self._paint_status(painter)
            if self._overlay_text:
                self._paint_overlay(painter)
        finally:
            painter.end()

    def _paint_status(self, painter: QPainter) -> None:
        """Always-on status block above the focus button."""
        if self._overlay_text:
            return  # overlay takes over
        host = ""
        connected = False
        if self._conn is not None:
            host = self._conn._hostname  # noqa: SLF001
            connected = self._conn.is_connected
        title = "RDP " + ("connected" if connected else "session")
        subtitle = (
            f"{host}\nRemote desktop runs in its own window\n"
            "(use the button below to bring it to the front)"
        ) if host else "Connecting..."

        title_font = QFont("JetBrains Mono", 18, QFont.Weight.Bold)
        sub_font = QFont("JetBrains Mono", 11)

        painter.setPen(QColor("#cdd6f4"))
        painter.setFont(title_font)
        title_rect = QRectF(0, self.height() / 2 - 110, self.width(), 36)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, title)

        painter.setPen(QColor("#a6adc8"))
        painter.setFont(sub_font)
        sub_rect = QRectF(0, self.height() / 2 - 60, self.width(), 70)
        painter.drawText(
            sub_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            subtitle,
        )

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
        painter.setBrush(QColor(30, 30, 46, 230))
        painter.drawRoundedRect(QRectF(rx, ry, tw + px * 2, th + py * 2), 8, 8)
        painter.setPen(self._overlay_color)
        painter.drawText(
            QRectF(0, 0, self.width(), self.height()),
            Qt.AlignmentFlag.AlignCenter,
            self._overlay_text,
        )
