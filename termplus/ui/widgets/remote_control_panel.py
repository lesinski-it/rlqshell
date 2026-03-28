"""Side panel with special key buttons for VNC/RDP remote desktop sessions."""

from __future__ import annotations

import asyncio
import logging
from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from termplus.app.constants import Colors

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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(48)
        self._conn = None
        self._protocol: str | None = None  # "vnc" or "rdp"

        # Sticky modifier states
        self._held: dict[str, bool] = {"ctrl": False, "alt": False, "win": False}

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

        layout.addStretch()

        self.setStyleSheet(
            f"RemoteControlPanel {{ background: {Colors.BG_DARKER}; "
            f"border-right: 1px solid {Colors.BORDER}; }}"
        )

    def set_connection(self, conn, protocol: str) -> None:
        """Attach the remote connection (VNCConnection or RDPConnection)."""
        self._conn = conn
        self._protocol = protocol

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

    # ------------------------------------------------------------------
    # Key combos
    # ------------------------------------------------------------------

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

    def __init__(
        self,
        display_widget: QWidget,
        conn,
        protocol: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._display = display_widget
        self._panel = RemoteControlPanel()
        self._panel.set_connection(conn, protocol)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._panel)
        layout.addWidget(display_widget, 1)

    # Proxy overlay API so ConnectionsPage can treat this like VNC/RDP widget
    def show_overlay(self, text: str, color: str | None = None) -> None:
        self._display.show_overlay(text, color)

    def clear_overlay(self) -> None:
        self._display.clear_overlay()

    def setFocus(self) -> None:
        self._display.setFocus()
