"""Port Forwarding page — runtime tunnel management (start/stop/monitor)."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import Colors
from rlqshell.core.host_manager import HostManager
from rlqshell.core.port_forward_manager import PortForwardManager
from rlqshell.core.tunnel_engine import TunnelEngine, TunnelState
from rlqshell.ui.dialogs.rule_editor_dialog import RuleEditorDialog
from rlqshell.ui.port_forward.tunnel_row import TunnelRow
from rlqshell.ui.widgets.empty_state import EmptyState

logger = logging.getLogger(__name__)


class PortForwardPage(QWidget):
    """Top-level page for managing active port forwarding tunnels."""

    tunnel_count_changed = Signal(int)
    navigate_to_vault = Signal()

    def __init__(
        self,
        pf_manager: PortForwardManager,
        tunnel_engine: TunnelEngine,
        host_manager: HostManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._pf = pf_manager
        self._engine = tunnel_engine
        self._hm = host_manager

        # rule_id -> TunnelRow
        self._rows: dict[int, TunnelRow] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setFixedHeight(52)
        toolbar.setStyleSheet(f"background-color: {Colors.BG_PRIMARY};")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(16, 8, 16, 8)
        tb.setSpacing(8)

        title = QLabel("Port Forwarding")
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        tb.addWidget(title)
        tb.addStretch()

        self._stop_all_btn = QPushButton("Stop All")
        self._stop_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_all_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {Colors.TEXT_SECONDARY}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 6px; "
            f"padding: 6px 14px; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: {Colors.BG_HOVER}; "
            f"color: {Colors.ERROR}; border-color: {Colors.ERROR}; }}"
        )
        self._stop_all_btn.clicked.connect(self._on_stop_all)
        tb.addWidget(self._stop_all_btn)

        add_btn = QPushButton("+ New Rule")
        add_btn.setProperty("cssClass", "primary")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(
            f"QPushButton {{ background-color: {Colors.ACCENT}; color: #fff; "
            f"border: none; border-radius: 6px; padding: 6px 14px; "
            f"font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: {Colors.ACCENT_HOVER}; }}"
        )
        add_btn.clicked.connect(self._on_new_rule)
        tb.addWidget(add_btn)

        layout.addWidget(toolbar)

        # Separator
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {Colors.BORDER};")
        layout.addWidget(sep)

        # Content area (scroll + empty state)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {Colors.BG_PRIMARY}; border: none; }}"
        )

        self._scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(0)
        self._scroll_layout.addStretch()
        self._scroll.setWidget(self._scroll_content)

        self._empty_state = EmptyState(
            title="No port forwarding rules",
            description="Create rules in the Vault or use the button above.",
            action_text="Go to Vault",
        )
        self._empty_state.action_clicked.connect(self.navigate_to_vault.emit)

        layout.addWidget(self._empty_state)
        layout.addWidget(self._scroll)

        # Wire engine signals
        self._engine.tunnel_state_changed.connect(self._on_tunnel_state_changed)
        self._engine.tunnel_error.connect(self._on_tunnel_error)

        self.refresh()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload rules from database and rebuild row list."""
        # Clear existing rows
        for row in self._rows.values():
            self._scroll_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()

        rules = self._pf.list_rules()
        hosts = {h.id: h.label or h.address for h in self._hm.list_hosts()}

        for rule in rules:
            host_label = hosts.get(rule.host_id, "Unknown host")
            row = TunnelRow(
                rule_id=rule.id,
                label=rule.label,
                host_label=host_label,
                direction=rule.direction,
                local_port=rule.local_port,
                remote_host=rule.remote_host,
                remote_port=rule.remote_port,
            )
            row.start_requested.connect(self._on_start)
            row.stop_requested.connect(self._on_stop)
            row.edit_requested.connect(self._on_edit_rule)
            row.delete_requested.connect(self._on_delete_rule)

            # Restore state if tunnel is already running
            info = self._engine.get_tunnel_info(rule.id)
            if info:
                row.set_state(info.state)
                if info.error_message:
                    row.set_error(info.error_message)

            self._rows[rule.id] = row
            # Insert before the stretch
            self._scroll_layout.insertWidget(self._scroll_layout.count() - 1, row)

        has_rules = len(rules) > 0
        self._empty_state.setVisible(not has_rules)
        self._scroll.setVisible(has_rules)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_start(self, rule_id: int) -> None:
        rule = self._pf.get_rule(rule_id)
        if rule:
            self._engine.start_tunnel(rule)

    def _on_stop(self, rule_id: int) -> None:
        self._engine.stop_tunnel(rule_id)

    def _on_stop_all(self) -> None:
        self._engine.stop_all()

    def _on_new_rule(self) -> None:
        editor = RuleEditorDialog(self._pf, self._hm, parent=self)
        if editor.exec() == RuleEditorDialog.DialogCode.Accepted:
            self.refresh()

    def _on_edit_rule(self, rule_id: int) -> None:
        # Stop tunnel before editing
        if self._engine.is_running(rule_id):
            self._engine.stop_tunnel(rule_id)
        editor = RuleEditorDialog(self._pf, self._hm, rule_id=rule_id, parent=self)
        if editor.exec() == RuleEditorDialog.DialogCode.Accepted:
            self.refresh()

    def _on_delete_rule(self, rule_id: int) -> None:
        if self._engine.is_running(rule_id):
            self._engine.stop_tunnel(rule_id)
        self._pf.delete_rule(rule_id)
        self.refresh()

    def _on_tunnel_state_changed(self, rule_id: int, state_str: str) -> None:
        row = self._rows.get(rule_id)
        if row is None:
            return
        try:
            state = TunnelState(state_str)
        except ValueError:
            return
        row.set_state(state)
        self.tunnel_count_changed.emit(self._engine.active_count())

    def _on_tunnel_error(self, rule_id: int, message: str) -> None:
        row = self._rows.get(rule_id)
        if row:
            row.set_error(message)
        from rlqshell.ui.widgets.toast import ToastManager
        ToastManager.instance().show_toast(
            f"Tunnel error: {message}", toast_type="error",
        )
