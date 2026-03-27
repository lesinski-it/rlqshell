"""Port forwarding rules view — list, create, edit, delete."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from termplus.app.constants import Colors
from termplus.core.host_manager import HostManager
from termplus.core.port_forward_manager import PortForwardManager, PortForwardRule

logger = logging.getLogger(__name__)


class _RuleEditor(QDialog):
    """Dialog for creating/editing a port forward rule."""

    def __init__(
        self,
        pf_manager: PortForwardManager,
        host_manager: HostManager,
        rule_id: int | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._pf = pf_manager
        self._hm = host_manager
        self._rule_id = rule_id

        self.setWindowTitle("Edit Rule" if rule_id else "New Port Forward Rule")
        self.setFixedSize(420, 400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        # Label
        layout.addWidget(self._lbl("Label"))
        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("e.g. MySQL tunnel")
        layout.addWidget(self._label_edit)

        # Host
        layout.addWidget(self._lbl("Host"))
        self._host_combo = QComboBox()
        for h in self._hm.list_hosts():
            self._host_combo.addItem(h.label or h.address, h.id)
        layout.addWidget(self._host_combo)

        # Direction
        layout.addWidget(self._lbl("Direction"))
        self._dir_combo = QComboBox()
        self._dir_combo.addItems(["local", "remote", "dynamic"])
        layout.addWidget(self._dir_combo)

        # Bind address
        layout.addWidget(self._lbl("Bind Address"))
        self._bind_edit = QLineEdit("127.0.0.1")
        layout.addWidget(self._bind_edit)

        # Ports row
        port_row = QHBoxLayout()
        port_row.setSpacing(12)

        left = QVBoxLayout()
        left.addWidget(self._lbl("Local Port"))
        self._local_port = QSpinBox()
        self._local_port.setRange(1, 65535)
        self._local_port.setValue(8080)
        left.addWidget(self._local_port)
        port_row.addLayout(left)

        right = QVBoxLayout()
        right.addWidget(self._lbl("Remote Host:Port"))
        rr = QHBoxLayout()
        self._remote_host = QLineEdit("localhost")
        rr.addWidget(self._remote_host)
        self._remote_port = QSpinBox()
        self._remote_port.setRange(1, 65535)
        self._remote_port.setValue(3306)
        rr.addWidget(self._remote_port)
        right.addLayout(rr)
        port_row.addLayout(right)

        layout.addLayout(port_row)

        # Auto-start
        self._auto_check = QCheckBox("Auto-start when connected")
        self._auto_check.setChecked(True)
        self._auto_check.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 13px;")
        layout.addWidget(self._auto_check)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("cancelBtn")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)

        save = QPushButton("Save")
        save.setObjectName("saveBtn")
        save.setDefault(True)
        save.clicked.connect(self._save)
        btn_row.addWidget(save)
        layout.addLayout(btn_row)

        self._apply_style()

        if rule_id:
            self._load(rule_id)

    def _load(self, rule_id: int) -> None:
        rule = self._pf.get_rule(rule_id)
        if not rule:
            return
        self._label_edit.setText(rule.label)
        idx = self._host_combo.findData(rule.host_id)
        if idx >= 0:
            self._host_combo.setCurrentIndex(idx)
        self._dir_combo.setCurrentText(rule.direction)
        self._bind_edit.setText(rule.bind_address)
        self._local_port.setValue(rule.local_port)
        self._remote_host.setText(rule.remote_host)
        if rule.remote_port:
            self._remote_port.setValue(rule.remote_port)
        self._auto_check.setChecked(rule.auto_start)

    def _save(self) -> None:
        rule = PortForwardRule(
            id=self._rule_id,
            host_id=self._host_combo.currentData() or 0,
            label=self._label_edit.text().strip(),
            direction=self._dir_combo.currentText(),
            bind_address=self._bind_edit.text().strip() or "127.0.0.1",
            local_port=self._local_port.value(),
            remote_host=self._remote_host.text().strip(),
            remote_port=self._remote_port.value(),
            auto_start=self._auto_check.isChecked(),
        )
        if self._rule_id:
            self._pf.update_rule(rule)
        else:
            self._pf.create_rule(rule)
        self.accept()

    def _lbl(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_SECONDARY}; "
            f"background: transparent;"
        )
        return l

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{ background-color: {Colors.BG_PRIMARY}; }}
            QLineEdit, QComboBox, QSpinBox {{
                background-color: {Colors.BG_SURFACE}; color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER}; border-radius: 6px;
                padding: 8px 12px; font-size: 13px;
            }}
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
                border-color: {Colors.ACCENT};
            }}
            QComboBox::drop-down {{ border: none; padding-right: 8px; }}
            QComboBox QAbstractItemView {{
                background-color: {Colors.BG_SURFACE}; color: {Colors.TEXT_PRIMARY};
                selection-background-color: {Colors.ACCENT}; border: 1px solid {Colors.BORDER};
            }}
            QPushButton#saveBtn {{
                background-color: {Colors.ACCENT}; color: #fff; border: none;
                border-radius: 6px; padding: 8px 20px; font-size: 13px; font-weight: 600;
            }}
            QPushButton#saveBtn:hover {{ background-color: {Colors.ACCENT_HOVER}; }}
            QPushButton#cancelBtn {{
                background: transparent; color: {Colors.TEXT_MUTED};
                border: 1px solid {Colors.BORDER}; border-radius: 6px;
                padding: 8px 16px; font-size: 13px;
            }}
            QPushButton#cancelBtn:hover {{ background-color: {Colors.BG_HOVER}; }}
        """)


class PortForwardView(QWidget):
    """Port forwarding rules table with CRUD."""

    def __init__(
        self,
        pf_manager: PortForwardManager,
        host_manager: HostManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._pf = pf_manager
        self._hm = host_manager

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

        add_btn = QPushButton("+ New Rule")
        add_btn.setProperty("cssClass", "primary")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_new_rule)
        tb.addWidget(add_btn)

        layout.addWidget(toolbar)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ["Label", "Host", "Direction", "Local Port", "Remote", "Auto"]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
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
        editor = _RuleEditor(self._pf, self._hm, parent=self)
        if editor.exec() == _RuleEditor.DialogCode.Accepted:
            self.refresh()

    def _on_context_menu(self, pos) -> None:
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
            editor = _RuleEditor(self._pf, self._hm, rule_id=rule_id, parent=self)
            if editor.exec() == _RuleEditor.DialogCode.Accepted:
                self.refresh()
        elif action == delete_action:
            self._pf.delete_rule(rule_id)
            self.refresh()
