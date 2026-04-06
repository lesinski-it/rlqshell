"""Single tunnel row widget — shows rule info, status badge, and start/stop control."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from termplus.app.constants import Colors
from termplus.core.tunnel_engine import TunnelState

_STATE_COLORS = {
    TunnelState.STOPPED: Colors.DISCONNECTED,
    TunnelState.STARTING: Colors.CONNECTING,
    TunnelState.ACTIVE: Colors.CONNECTED,
    TunnelState.ERROR: Colors.ERROR,
    TunnelState.STOPPING: Colors.CONNECTING,
}

_STATE_LABELS = {
    TunnelState.STOPPED: "Stopped",
    TunnelState.STARTING: "Starting...",
    TunnelState.ACTIVE: "Active",
    TunnelState.ERROR: "Error",
    TunnelState.STOPPING: "Stopping...",
}

_DIRECTION_ARROWS = {
    "local": "\u2192",    # →
    "remote": "\u2190",   # ←
    "dynamic": "\u21C4",  # ⇄
}


class TunnelRow(QWidget):
    """A single row representing a port forward rule with live status."""

    start_requested = Signal(int)   # rule_id
    stop_requested = Signal(int)    # rule_id
    edit_requested = Signal(int)    # rule_id
    delete_requested = Signal(int)  # rule_id

    def __init__(
        self,
        rule_id: int,
        label: str,
        host_label: str,
        direction: str,
        local_port: int,
        remote_host: str,
        remote_port: int | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._rule_id = rule_id
        self._state = TunnelState.STOPPED

        self.setFixedHeight(50)
        self.setStyleSheet(
            f"TunnelRow {{ background-color: {Colors.BG_PRIMARY}; "
            f"border-bottom: 1px solid {Colors.BORDER}; }}"
        )
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        # Label
        self._label = QLabel(label or "Untitled")
        self._label.setFixedWidth(150)
        self._label.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        layout.addWidget(self._label)

        # Host
        host_lbl = QLabel(host_label)
        host_lbl.setFixedWidth(120)
        host_lbl.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        layout.addWidget(host_lbl)

        # Direction + ports
        arrow = _DIRECTION_ARROWS.get(direction, "?")
        if direction == "local":
            port_text = f":{local_port} {arrow} {remote_host}:{remote_port}"
        elif direction == "remote":
            port_text = f":{remote_port or '?'} {arrow} {remote_host or 'localhost'}:{local_port}"
        else:
            port_text = f":{local_port} (SOCKS5)"

        dir_label = QLabel(f"{direction.upper()}  {port_text}")
        dir_label.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_MUTED}; background: transparent; "
            f"font-family: 'Consolas', 'Courier New', monospace;"
        )
        layout.addWidget(dir_label, 1)

        # Status badge
        self._status_badge = QLabel(_STATE_LABELS[TunnelState.STOPPED])
        self._status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_badge.setFixedSize(80, 30)
        self._update_badge_style(TunnelState.STOPPED)
        layout.addWidget(self._status_badge)

        # Start/Stop button
        self._action_btn = QPushButton("Start")
        self._action_btn.setFixedSize(80, 30)
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_btn.clicked.connect(self._on_action)
        self._update_action_btn_style()
        layout.addWidget(self._action_btn)

    @property
    def rule_id(self) -> int:
        return self._rule_id

    def set_state(self, state: TunnelState) -> None:
        self._state = state
        self._status_badge.setText(_STATE_LABELS.get(state, "Unknown"))
        self._update_badge_style(state)
        self._update_action_btn_style()

    def set_error(self, message: str) -> None:
        self._status_badge.setToolTip(message)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_action(self) -> None:
        if self._state in (TunnelState.ACTIVE, TunnelState.STARTING):
            self.stop_requested.emit(self._rule_id)
        else:
            self.start_requested.emit(self._rule_id)

    def _on_context_menu(self, pos) -> None:
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        edit_action = menu.addAction("Edit")
        menu.addSeparator()
        delete_action = menu.addAction("Delete")

        action = menu.exec(self.mapToGlobal(pos))
        if action == edit_action:
            self.edit_requested.emit(self._rule_id)
        elif action == delete_action:
            self.delete_requested.emit(self._rule_id)

    def _update_badge_style(self, state: TunnelState) -> None:
        color = _STATE_COLORS.get(state, Colors.DISCONNECTED)
        self._status_badge.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {color}; "
            f"background: transparent; padding: 2px 8px; "
            f"border: 1px solid {color}; border-radius: 4px;"
        )

    def _update_action_btn_style(self) -> None:
        is_running = self._state in (TunnelState.ACTIVE, TunnelState.STARTING)
        self._action_btn.setText("Stop" if is_running else "Start")

        if is_running:
            self._action_btn.setStyleSheet(
                f"QPushButton {{ background-color: {Colors.ERROR}; color: #fff; "
                f"border: none; border-radius: 4px; padding: 4px 12px; "
                f"font-size: 12px; font-weight: 600; }}"
                f"QPushButton:hover {{ background-color: #c0392b; }}"
            )
        else:
            self._action_btn.setStyleSheet(
                f"QPushButton {{ background-color: {Colors.ACCENT}; color: #fff; "
                f"border: none; border-radius: 4px; padding: 4px 12px; "
                f"font-size: 12px; font-weight: 600; }}"
                f"QPushButton:hover {{ background-color: {Colors.ACCENT_HOVER}; }}"
            )
        self._action_btn.setEnabled(
            self._state not in (TunnelState.STARTING, TunnelState.STOPPING)
        )
