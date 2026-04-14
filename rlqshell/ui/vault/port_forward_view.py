"""Port forwarding rules view — list, create, edit, delete."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import Colors
from rlqshell.core.host_manager import HostManager
from rlqshell.core.port_forward_manager import PortForwardManager
from rlqshell.ui.dialogs.rule_editor_dialog import RuleEditorDialog

logger = logging.getLogger(__name__)


class PortForwardView(QWidget):
    """Port forwarding rules table with CRUD."""

    def __init__(
        self,
        pf_manager: PortForwardManager,
        host_manager: HostManager,
        vault_locked: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._pf = pf_manager
        self._hm = host_manager
        self._vault_locked = vault_locked

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

        title = QLabel("Tunneling")
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        tb.addWidget(title)
        tb.addStretch()

        add_btn = QPushButton("+ New Rule")
        add_btn.setProperty("cssClass", "primary")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_new_rule)
        if vault_locked:
            add_btn.setEnabled(False)
            add_btn.setToolTip("Vault is locked \u2014 enter master password at startup")
        tb.addWidget(add_btn)

        layout.addWidget(toolbar)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ["Label", "Host", "Direction", "Local Port", "Remote", "Auto"]
        )
        header = self._table.horizontalHeader()
        # Size every column to its actual text content; Qt re-measures
        # automatically when the font or data changes. Stretch the last
        # visible section so any remaining horizontal space is consumed.
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {Colors.BG_PRIMARY}; color: {Colors.TEXT_PRIMARY};
                border: none; gridline-color: {Colors.BORDER}; font-size: 12px;
            }}
            QTableWidget::item {{ padding: 6px 8px; }}
            QTableWidget::item:selected {{ background-color: {Colors.BG_SURFACE}; }}
            QHeaderView::section {{
                background-color: {Colors.BG_DARKER}; color: {Colors.TEXT_SECONDARY};
                font-weight: 600; font-size: 11px; padding: 6px 8px;
                border: none; border-bottom: 1px solid {Colors.BORDER};
            }}
        """)
        layout.addWidget(self._table)

        self.refresh()

    def refresh(self) -> None:
        rules = self._pf.list_rules()
        hosts = {h.id: h.label or h.address for h in self._hm.list_hosts()}

        self._table.setRowCount(len(rules))
        for i, rule in enumerate(rules):
            self._table.setItem(i, 0, QTableWidgetItem(rule.label))
            self._table.setItem(i, 1, QTableWidgetItem(hosts.get(rule.host_id, "?")))
            self._table.setItem(i, 2, QTableWidgetItem(rule.direction))
            self._table.setItem(i, 3, QTableWidgetItem(str(rule.local_port)))
            remote = f"{rule.remote_host}:{rule.remote_port}" if rule.remote_port else rule.remote_host
            self._table.setItem(i, 4, QTableWidgetItem(remote))
            self._table.setItem(i, 5, QTableWidgetItem("Yes" if rule.auto_start else "No"))

            # Store rule_id for context menu
            for col in range(6):
                self._table.item(i, col).setData(Qt.ItemDataRole.UserRole, rule.id)

    def _on_new_rule(self) -> None:
        editor = RuleEditorDialog(self._pf, self._hm, parent=self)
        if editor.exec() == RuleEditorDialog.DialogCode.Accepted:
            self.refresh()

    def _on_context_menu(self, pos) -> None:
        if self._vault_locked:
            return
        item = self._table.itemAt(pos)
        if not item:
            return
        rule_id = item.data(Qt.ItemDataRole.UserRole)
        if not rule_id:
            return

        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        edit_action = menu.addAction("Edit")
        menu.addSeparator()
        delete_action = menu.addAction("Delete")

        action = menu.exec(self._table.viewport().mapToGlobal(pos))
        if action == edit_action:
            editor = RuleEditorDialog(self._pf, self._hm, rule_id=rule_id, parent=self)
            if editor.exec() == RuleEditorDialog.DialogCode.Accepted:
                self.refresh()
        elif action == delete_action:
            self._pf.delete_rule(rule_id)
            self.refresh()
