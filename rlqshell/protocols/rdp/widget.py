"""RDP display widget — hosts an embedded FreeRDP window.

Acts as a parent container: FreeRDP draws the remote desktop into a child
native window we own (passed via /parent-window:<HWND>). All keyboard, mouse
and device events are handled by FreeRDP directly. We only paint a status
overlay (connecting / error) on top.
"""

from __future__ import annotations

import ctypes
import logging
import sys

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPaintEvent
from PySide6.QtWidgets import QPushButton, QSizePolicy, QWidget

from rlqshell.protocols.rdp.connection import RDPConnection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Win32 helpers for managing the embedded FreeRDP child window
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    _SWP_NOMOVE = 0x0002
    _SWP_NOZORDER = 0x0004
    _SWP_NOACTIVATE = 0x0010
    _SWP_SHOWWINDOW = 0x0040
    _SWP_FRAMECHANGED = 0x0020

    # EnumChildWindows callback signature
    _EnumChildProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p,
    )

    # Argument types -- without these, ctypes may marshal HWND (a 64-bit
    # pointer) as 32-bit on x64 Python and silently truncate the handle.
    _user32.EnumChildWindows.argtypes = [
        ctypes.c_void_p, _EnumChildProc, ctypes.c_void_p,
    ]
    _user32.EnumChildWindows.restype = ctypes.c_bool
    _user32.SetWindowPos.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint,
    ]
    _user32.SetWindowPos.restype = ctypes.c_bool
    _user32.SetFocus.argtypes = [ctypes.c_void_p]
    _user32.SetFocus.restype = ctypes.c_void_p
    _user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    _user32.SetForegroundWindow.restype = ctypes.c_bool
    _user32.BringWindowToTop.argtypes = [ctypes.c_void_p]
    _user32.BringWindowToTop.restype = ctypes.c_bool
    _user32.GetWindowThreadProcessId.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong),
    ]
    _user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
    _user32.AttachThreadInput.argtypes = [
        ctypes.c_ulong, ctypes.c_ulong, ctypes.c_bool,
    ]
    _user32.AttachThreadInput.restype = ctypes.c_bool
    _user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    _user32.IsWindowVisible.restype = ctypes.c_bool
    _user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _user32.ShowWindow.restype = ctypes.c_bool
    _SW_SHOW = 5
    _user32.GetClientRect.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(wintypes.RECT),
    ]
    _user32.GetClientRect.restype = ctypes.c_bool
    _user32.GetClassNameW.argtypes = [
        ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int,
    ]
    _user32.GetClassNameW.restype = ctypes.c_int
    _kernel32.GetCurrentThreadId.restype = ctypes.c_ulong

    def _window_class(hwnd: int) -> str:
        buf = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(hwnd, buf, 256)
        return buf.value or ""

    def _find_child_hwnd(parent_hwnd: int) -> int | None:
        """Find the embedded FreeRDP rendering surface inside our parent HWND.

        EnumChildWindows recurses through the full descendant tree and
        every kind of window FreeRDP creates is in there: a top-level
        container, the actual canvas it paints into, hidden message-only
        windows, possibly tooltip windows. We log every candidate at
        DEBUG and pick the largest *visible* one as the rendering
        surface (sized to /size: -- almost certainly the largest area).
        """
        if not parent_hwnd:
            return None
        found: list[dict] = []

        def _cb(hwnd, _lparam):
            try:
                rect = wintypes.RECT()
                _user32.GetClientRect(hwnd, ctypes.byref(rect))
                found.append({
                    "hwnd": int(hwnd),
                    "visible": bool(_user32.IsWindowVisible(hwnd)),
                    "w": int(rect.right),
                    "h": int(rect.bottom),
                    "class": _window_class(hwnd),
                })
            except Exception:
                pass
            return True

        try:
            _user32.EnumChildWindows(parent_hwnd, _EnumChildProc(_cb), None)
        except Exception:
            return None

        if not found:
            return None
        for c in found:
            logger.debug("RDP candidate child: %s", c)

        # Largest visible window in the descendant tree -- this matches the
        # FreeRDP rendering surface in every layout we've seen.
        visible = [c for c in found if c["visible"] and c["w"] > 0 and c["h"] > 0]
        chosen = max(visible, key=lambda c: c["w"] * c["h"]) if visible else found[0]
        logger.info(
            "RDP child picked: hwnd=%s class=%r %dx%d (out of %d candidates)",
            chosen["hwnd"], chosen.get("class", ""),
            chosen.get("w", 0), chosen.get("h", 0), len(found),
        )
        return chosen["hwnd"]

    def _resize_child(hwnd: int, width: int, height: int) -> None:
        """Resize+move+show a child window to fill (0,0)-(width,height)."""
        # ShowWindow first -- some FreeRDP builds create the window with
        # WS_VISIBLE off and rely on the parent to make it visible.
        _user32.ShowWindow(hwnd, _SW_SHOW)
        ok = _user32.SetWindowPos(
            hwnd, None, 0, 0, max(1, width), max(1, height),
            _SWP_NOZORDER | _SWP_NOACTIVATE | _SWP_SHOWWINDOW | _SWP_FRAMECHANGED,
        )
        # Verify what FreeRDP actually got
        rect = wintypes.RECT()
        _user32.GetClientRect(hwnd, ctypes.byref(rect))
        logger.info(
            "SetWindowPos(hwnd=%s req=%dx%d) ok=%s -> client now %dx%d",
            hwnd, width, height, ok, rect.right, rect.bottom,
        )

    def _focus_window(hwnd: int) -> None:
        """Move keyboard focus to the given HWND across processes.

        SetFocus is silently ignored when the target window belongs to
        another thread (xfreerdp runs in a separate process), so we
        attach the input queues for the duration of the call. We also
        call BringWindowToTop so the embedded canvas is on the Z-order
        top and ready to receive keystrokes.
        """
        if not hwnd:
            return
        try:
            target_thread = _user32.GetWindowThreadProcessId(hwnd, None)
            current_thread = _kernel32.GetCurrentThreadId()
            attached = False
            if target_thread and target_thread != current_thread:
                attached = bool(_user32.AttachThreadInput(
                    current_thread, target_thread, True,
                ))
            try:
                _user32.BringWindowToTop(hwnd)
                _user32.SetFocus(hwnd)
            finally:
                if attached:
                    _user32.AttachThreadInput(
                        current_thread, target_thread, False,
                    )
        except Exception:
            logger.debug("SetFocus failed for HWND %s", hwnd, exc_info=True)
else:  # non-Windows fallbacks (Linux/macOS handled separately later)
    def _find_child_hwnd(parent_hwnd: int) -> int | None:  # noqa: ARG001
        return None

    def _resize_child(hwnd: int, width: int, height: int) -> None:  # noqa: ARG001
        pass

    def _focus_window(hwnd: int) -> None:  # noqa: ARG001
        pass


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

        # Embedded FreeRDP child window state. xfreerdp creates its own native
        # window, reparents it to our HWND via /parent-window, then we manage
        # its size and focus from here so it tracks the Qt widget.
        self._child_hwnd: int | None = None
        self._child_poll_attempts = 0
        self._child_finder = QTimer(self)
        self._child_finder.setInterval(150)
        self._child_finder.timeout.connect(self._poll_for_child)

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
        # Reconnect tears down the old xfreerdp process; the child HWND is
        # now stale and a new one will appear once the new process spawns.
        self._child_hwnd = None
        self._child_poll_attempts = 0
        if sys.platform == "win32":
            self._child_finder.start()
            logger.info("RDPWidget: child window poller started")

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
    # Embedded child window management (Win32 only for now)
    # ------------------------------------------------------------------

    def _poll_for_child(self) -> None:
        """Look for the FreeRDP child window xfreerdp creates after spawn."""
        if self._child_hwnd is not None:
            self._child_finder.stop()
            return
        self._child_poll_attempts += 1
        try:
            parent = int(self.winId())
        except Exception:
            return
        child = _find_child_hwnd(parent)
        if child:
            self._child_hwnd = child
            self._child_finder.stop()
            logger.info(
                "RDP child HWND captured after %d polls: parent=%s child=%s",
                self._child_poll_attempts, parent, child,
            )
            self._resize_child_to_widget()
            _focus_window(child)
        elif self._child_poll_attempts in (40, 100):
            # ~6 s and ~15 s in -- if still nothing, surface it loudly.
            logger.warning(
                "RDPWidget: still no child window for parent HWND %s after %d "
                "polls. xfreerdp /parent-window may not be embedding correctly.",
                parent, self._child_poll_attempts,
            )
        elif self._child_poll_attempts >= 200:
            # ~30 s -- give up so we don't poll forever.
            self._child_finder.stop()
            logger.error(
                "RDPWidget: child window not found after %d polls; giving up. "
                "RDP keyboard/resize will not work for this session.",
                self._child_poll_attempts,
            )

    def _resize_child_to_widget(self) -> None:
        if self._child_hwnd is None:
            return
        w, h = self.width(), self.height()
        logger.info("Resizing FreeRDP child to widget size %dx%d", w, h)
        _resize_child(self._child_hwnd, w, h)

    def resizeEvent(self, event) -> None:  # noqa: N802 -- Qt API
        super().resizeEvent(event)
        if self._reconnect_btn is not None and self._reconnect_btn.isVisible():
            self._position_reconnect_btn()
        self._resize_child_to_widget()

    def focusInEvent(self, event) -> None:  # noqa: N802 -- Qt API
        super().focusInEvent(event)
        if self._child_hwnd is not None:
            _focus_window(self._child_hwnd)

    def mousePressEvent(self, event) -> None:  # noqa: N802 -- Qt API
        super().mousePressEvent(event)
        # Clicks on the embedded RDP area normally route directly to the
        # child window, but if the user clicks on the surrounding overlay
        # (e.g. the dark background frame around the framebuffer) we still
        # want keyboard focus to land on the RDP session afterwards.
        if self._child_hwnd is not None:
            _focus_window(self._child_hwnd)

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
