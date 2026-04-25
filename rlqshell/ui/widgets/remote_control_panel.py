"""Side panel with special key buttons for VNC/RDP remote desktop sessions."""

from __future__ import annotations

import asyncio
import logging
from functools import partial

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import Colors
from rlqshell.protocols.clipboard_bridge import ClipboardBridge

logger = logging.getLogger(__name__)

# Key definitions: VNC keysyms and RDP scancodes
_KEYS = {
    "ctrl":  {"vnc": 0xFFE3, "rdp": (0x1D, False)},
    "alt":   {"vnc": 0xFFE9, "rdp": (0x38, False)},
    "win":   {"vnc": 0xFFEB, "rdp": (0x5B, True)},
    "del":   {"vnc": 0xFFFF, "rdp": (0x53, True)},
    "tab":   {"vnc": 0xFF09, "rdp": (0x0F, False)},
    "esc":   {"vnc": 0xFF1B, "rdp": (0x01, False)},
    "prtsc": {"vnc": 0xFF61, "rdp": (0x37, True)},
    "f11":   {"vnc": 0xFFC8, "rdp": (0x57, False)},
}


class RemoteControlPanel(QWidget):
    """Narrow side panel with toggle keys and key-combo buttons."""

    fullscreen_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(48)
        self._conn = None
        self._protocol: str | None = None  # "vnc" or "rdp"

        # Sticky modifier states
        self._held: dict[str, bool] = {"ctrl": False, "alt": False, "win": False}

        # Paste-as-typing state
        self._typing_task = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(4)

        # Toggle modifiers
        self._ctrl_btn = self._make_button("Ctrl", partial(self._toggle_mod, "ctrl"))
        layout.addWidget(self._ctrl_btn)

        self._alt_btn = self._make_button("Alt", partial(self._toggle_mod, "alt"))
        layout.addWidget(self._alt_btn)

        self._win_btn = self._make_button("\u229e", partial(self._toggle_mod, "win"))
        self._win_btn.setToolTip("Windows / Super")
        layout.addWidget(self._win_btn)

        # Separator
        layout.addSpacing(8)

        # Combo / action buttons
        cad_btn = self._make_button("C+A+D", self._send_ctrl_alt_del)
        cad_btn.setToolTip("Ctrl + Alt + Del")
        layout.addWidget(cad_btn)

        tab_btn = self._make_button("Tab", partial(self._send_tap, "tab"))
        layout.addWidget(tab_btn)

        esc_btn = self._make_button("Esc", partial(self._send_tap, "esc"))
        layout.addWidget(esc_btn)

        prt_btn = self._make_button("PrSc", partial(self._send_tap, "prtsc"))
        prt_btn.setToolTip("Print Screen")
        layout.addWidget(prt_btn)

        # VNC-only: typed paste from clipboard (for servers like QEMU-VNC
        # that don't implement cut-text). Hidden for RDP (its CLIPRDR works).
        self._paste_btn = self._make_button("Wklej", self._paste_typed)
        self._paste_btn.setToolTip(
            "Wklej tekst ze schowka jako wpisywany z klawiatury\n"
            "(dla VNC serwer\u00f3w bez obs\u0142ugi cut-text, np. QEMU)"
        )
        self._paste_btn.hide()
        layout.addWidget(self._paste_btn)

        # Separator
        layout.addSpacing(8)

        self._fs_btn = self._make_button("\u26f6", self._toggle_fullscreen)
        self._fs_btn.setToolTip("Toggle fullscreen")
        layout.addWidget(self._fs_btn)

        layout.addStretch()

        self.setStyleSheet(
            f"RemoteControlPanel {{ background: {Colors.BG_DARKER}; "
            f"border-right: 1px solid {Colors.BORDER}; }}"
        )

    def set_connection(self, conn, protocol: str) -> None:
        """Attach the remote connection (VNCConnection or RDPConnection)."""
        self._conn = conn
        self._protocol = protocol
        self._paste_btn.setVisible(protocol == "vnc")

    # ------------------------------------------------------------------
    # Button factory
    # ------------------------------------------------------------------

    @staticmethod
    def _make_button(text: str, callback) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(40, 32)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.clicked.connect(callback)
        btn.setStyleSheet(
            f"QPushButton {{ background: {Colors.BG_SURFACE}; color: {Colors.TEXT_PRIMARY}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 4px; "
            f"font-size: 10px; font-weight: 600; padding: 2px; }}"
            f"QPushButton:hover {{ background: {Colors.BG_HOVER}; }}"
            f"QPushButton:pressed {{ background: {Colors.BG_ACTIVE}; }}"
        )
        return btn

    def _update_toggle_style(self, btn: QPushButton, active: bool) -> None:
        if active:
            btn.setStyleSheet(
                f"QPushButton {{ background: {Colors.ACCENT}; color: #fff; "
                f"border: 1px solid {Colors.ACCENT}; border-radius: 4px; "
                f"font-size: 10px; font-weight: 600; padding: 2px; }}"
                f"QPushButton:hover {{ background: {Colors.ACCENT_HOVER}; }}"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton {{ background: {Colors.BG_SURFACE}; color: {Colors.TEXT_PRIMARY}; "
                f"border: 1px solid {Colors.BORDER}; border-radius: 4px; "
                f"font-size: 10px; font-weight: 600; padding: 2px; }}"
                f"QPushButton:hover {{ background: {Colors.BG_HOVER}; }}"
                f"QPushButton:pressed {{ background: {Colors.BG_ACTIVE}; }}"
            )

    # ------------------------------------------------------------------
    # Key sending helpers
    # ------------------------------------------------------------------

    def _send_key(self, key_name: str, pressed: bool) -> None:
        """Send a key press/release to the remote session."""
        if not self._conn or not self._protocol:
            return
        spec = _KEYS.get(key_name)
        if not spec:
            return

        if self._protocol == "vnc":
            keysym = spec["vnc"]
            self._conn.send_key_event(pressed, keysym)
        elif self._protocol == "rdp":
            scancode, extended = spec["rdp"]
            try:
                asyncio.ensure_future(
                    self._conn._send_key_scancode(scancode, pressed, extended),
                )
            except RuntimeError:
                pass

    def _send_tap(self, key_name: str) -> None:
        """Press and release a key."""
        self._send_key(key_name, True)
        self._send_key(key_name, False)

    # ------------------------------------------------------------------
    # Toggle modifiers (sticky keys)
    # ------------------------------------------------------------------

    def _toggle_mod(self, key_name: str) -> None:
        """Toggle a sticky modifier key."""
        btn_map = {"ctrl": self._ctrl_btn, "alt": self._alt_btn, "win": self._win_btn}
        btn = btn_map.get(key_name)
        if btn is None:
            return

        self._held[key_name] = not self._held[key_name]
        active = self._held[key_name]
        self._send_key(key_name, active)
        self._update_toggle_style(btn, active)

    def release_all_modifiers(self) -> None:
        """Release all held modifiers."""
        for key_name in list(self._held):
            if self._held[key_name]:
                self._toggle_mod(key_name)

    def _toggle_fullscreen(self) -> None:
        self.fullscreen_requested.emit()

    # ------------------------------------------------------------------
    # Key combos
    # ------------------------------------------------------------------

    def _paste_typed(self) -> None:
        """Send QClipboard text to the remote as a stream of key presses.

        Click toggles between start/stop for long pastes (shows progress as %).
        """
        if self._protocol != "vnc" or self._conn is None:
            return

        # If a paste is in progress, cancel it
        if self._typing_task and not self._typing_task.done():
            try:
                self._typing_task.cancel()
                logger.info("Paste-as-typing cancelled by user")
            except Exception:
                pass
            self._typing_task = None
            self._paste_btn.setText("Wklej")
            self._paste_btn.setEnabled(True)
            return

        text = QApplication.clipboard().text()
        if not text:
            logger.info("Paste-as-typing skipped: clipboard is empty")
            return

        self._paste_btn.setEnabled(False)
        self._paste_btn.setText("0%")

        def _progress(done: int, total: int) -> None:
            pct = int(done * 100 / total) if total else 100
            self._paste_btn.setText(f"{pct}%")
            if done >= total:
                self._paste_btn.setText("Wklej")
                self._paste_btn.setEnabled(True)

        try:
            # Get VNC paste delay from config
            delay_ms = 5  # default
            try:
                app = QApplication.instance()
                config = getattr(app, "config", None)
                if config:
                    delay_ms = config.get("clipboard.vnc_paste_delay_ms", 5)
            except Exception:
                pass

            self._typing_task = asyncio.ensure_future(
                self._conn.send_typed_text(text, delay_ms=delay_ms, progress_cb=_progress),
            )
        except RuntimeError:
            logger.debug("no running loop for send_typed_text")
            self._paste_btn.setText("Wklej")
            self._paste_btn.setEnabled(True)

    def _send_ctrl_alt_del(self) -> None:
        """Send Ctrl+Alt+Del combo."""
        self._send_key("ctrl", True)
        self._send_key("alt", True)
        self._send_key("del", True)
        self._send_key("del", False)
        self._send_key("alt", False)
        self._send_key("ctrl", False)

        # Reset toggle states if they were held
        for key_name in ("ctrl", "alt"):
            if self._held[key_name]:
                self._held[key_name] = False
                btn = {"ctrl": self._ctrl_btn, "alt": self._alt_btn}[key_name]
                self._update_toggle_style(btn, False)


class RemoteDesktopContainer(QWidget):
    """Wraps a VNC/RDP display widget with a RemoteControlPanel."""

    fullscreen_requested = Signal()
    reconnect_requested = Signal()

    _PANEL_WIDTH = 48
    _ANIM_MS = 180

    def __init__(
        self,
        display_widget: QWidget,
        conn,
        protocol: str,
        parent: QWidget | None = None,
        enable_clipboard: bool = True,
    ) -> None:
        super().__init__(parent)
        self._display = display_widget
        # Panel is an overlay child (not in layout) — floats above the display
        self._panel = RemoteControlPanel(self)
        self._panel.set_connection(conn, protocol)
        self._panel.fullscreen_requested.connect(self.fullscreen_requested)
        self._panel_visible = True
        self._bridge: ClipboardBridge | None = (
            ClipboardBridge(conn, protocol, self) if enable_clipboard else None
        )
        # Forward the display's reconnect_requested signal up to ConnectionsPage
        if hasattr(display_widget, "reconnect_requested"):
            display_widget.reconnect_requested.connect(self.reconnect_requested)

        # Floating Proxmox-style tab handle
        self._toggle_btn = QPushButton("\u2039", self)  # ‹
        self._toggle_btn.setFixedSize(14, 38)
        self._toggle_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setToolTip("Hide / show key panel")
        self._toggle_btn.clicked.connect(self._toggle_panel)
        self._toggle_btn.setStyleSheet(
            f"QPushButton {{ background: {Colors.BG_SURFACE}; color: {Colors.TEXT_SECONDARY}; "
            f"border: 1px solid {Colors.BORDER}; border-left: none; "
            f"border-top-right-radius: 6px; border-bottom-right-radius: 6px; "
            f"font-size: 10px; padding: 0; }}"
            f"QPushButton:hover {{ background: {Colors.BG_HOVER}; color: {Colors.TEXT_PRIMARY}; }}"
        )

        # Auto-hide timer: collapses panel after 3 s without hover
        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.setInterval(3000)
        self._auto_hide_timer.timeout.connect(self._auto_hide)
        self._panel.installEventFilter(self)
        self._toggle_btn.installEventFilter(self)

        # Slide animation — moves panel left/right (pos), display stays full-width
        self._anim = QPropertyAnimation(self._panel, b"pos")
        self._anim.setDuration(self._ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._anim.valueChanged.connect(
            lambda v: self._toggle_btn.move(max(0, v.x() + self._PANEL_WIDTH), 72)
        )

        # display_widget fills the container via layout; panel is a free overlay
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(display_widget, 1)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._panel.resize(self._PANEL_WIDTH, self.height())
        self._toggle_btn.move(self._PANEL_WIDTH, 72)
        self._panel.raise_()
        self._toggle_btn.raise_()
        self._auto_hide_timer.start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._panel.resize(self._PANEL_WIDTH, self.height())
        self._toggle_btn.move(max(0, self._panel.x() + self._PANEL_WIDTH), 72)
        self._panel.raise_()
        self._toggle_btn.raise_()

    def eventFilter(self, obj, event) -> bool:
        if obj in (self._panel, self._toggle_btn):
            t = event.type()
            if t == QEvent.Type.Enter:
                self._auto_hide_timer.stop()
            elif t == QEvent.Type.Leave:
                # Brief delay so moving between panel↔toggle doesn't trigger hide
                QTimer.singleShot(120, self._schedule_hide)
        return super().eventFilter(obj, event)

    def _schedule_hide(self) -> None:
        if not (self._panel.underMouse() or self._toggle_btn.underMouse()):
            if self._panel_visible:
                self._auto_hide_timer.start()

    def _auto_hide(self) -> None:
        if self._panel_visible:
            self._toggle_panel()

    def _toggle_panel(self) -> None:
        self._anim.stop()
        if self._panel_visible:
            self._auto_hide_timer.stop()
            self._anim.setStartValue(QPoint(0, 0))
            self._anim.setEndValue(QPoint(-self._PANEL_WIDTH, 0))
            self._toggle_btn.setText("\u203a")  # ›
        else:
            self._anim.setStartValue(QPoint(-self._PANEL_WIDTH, 0))
            self._anim.setEndValue(QPoint(0, 0))
            self._toggle_btn.setText("\u2039")  # ‹
            self._auto_hide_timer.start()
        self._panel_visible = not self._panel_visible
        self._anim.start()

    # Proxy overlay API so ConnectionsPage can treat this like VNC/RDP widget
    def show_overlay(
        self,
        text: str,
        color: str | None = None,
        show_reconnect: bool = False,
    ) -> None:
        self._display.show_overlay(text, color, show_reconnect=show_reconnect)

    def clear_overlay(self) -> None:
        self._display.clear_overlay()

    @property
    def display_widget(self) -> QWidget:
        return self._display

    def set_connection(self, conn, protocol: str, enable_clipboard: bool = True) -> None:
        """Re-wire the panel and underlying display widget to a new connection."""
        self._panel.set_connection(conn, protocol)
        if hasattr(self._display, "set_connection"):
            self._display.set_connection(conn)
        if self._bridge is not None:
            self._bridge.detach()
            self._bridge = None
        if enable_clipboard:
            self._bridge = ClipboardBridge(conn, protocol, self)

    def closeEvent(self, event) -> None:
        if self._bridge is not None:
            self._bridge.detach()
            self._bridge = None
        super().closeEvent(event)

    def setFocus(self) -> None:
        self._display.setFocus()
