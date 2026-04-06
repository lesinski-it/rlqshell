"""Shared dialog for creating/editing a port forward rule."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from termplus.app.constants import Colors
from termplus.core.host_manager import HostManager
from termplus.core.port_forward_manager import PortForwardManager, PortForwardRule

logger = logging.getLogger(__name__)


class RuleEditorDialog(QDialog):
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
        self.setFixedSize(500, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        # Label
        layout.addWidget(self._lbl("Label"))
        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("e.g. MySQL tunnel")
        layout.addWidget(self._label_edit)

        # Host + Direction row
        host_dir_row = QHBoxLayout()
        host_dir_row.setSpacing(16)

        host_col = QVBoxLayout()
        host_col.setSpacing(4)
        host_col.addWidget(self._lbl("Host"))
        self._host_combo = QComboBox()
        for h in self._hm.list_hosts():
            self._host_combo.addItem(h.label or h.address, h.id)
        host_col.addWidget(self._host_combo)
        host_dir_row.addLayout(host_col, 2)

        dir_col = QVBoxLayout()
        dir_col.setSpacing(4)
        dir_col.addWidget(self._lbl("Direction"))
        self._dir_combo = QComboBox()
        self._dir_combo.addItems(["local", "remote", "dynamic"])
        dir_col.addWidget(self._dir_combo)
        host_dir_row.addLayout(dir_col, 1)

        layout.addLayout(host_dir_row)

        # Bind address
        layout.addWidget(self._lbl("Bind Address"))
        self._bind_edit = QLineEdit("127.0.0.1")
        layout.addWidget(self._bind_edit)

        # Local Port
        layout.addWidget(self._lbl("Local Port"))
        self._local_port = QSpinBox()
        self._local_port.setRange(1, 65535)
        self._local_port.setValue(8080)
        layout.addWidget(self._local_port)

        # Remote Host + Port row
        remote_row = QHBoxLayout()
        remote_row.setSpacing(16)

        rh_col = QVBoxLayout()
        rh_col.setSpacing(4)
        rh_col.addWidget(self._lbl("Remote Host"))
        self._remote_host = QLineEdit("localhost")
        rh_col.addWidget(self._remote_host)
        remote_row.addLayout(rh_col, 2)

        rp_col = QVBoxLayout()
        rp_col.setSpacing(4)
        rp_col.addWidget(self._lbl("Remote Port"))
        self._remote_port = QSpinBox()
        self._remote_port.setRange(1, 65535)
        self._remote_port.setValue(3306)
        rp_col.addWidget(self._remote_port)
        remote_row.addLayout(rp_col, 1)

        layout.addLayout(remote_row)

        # Auto-start
        layout.addSpacing(4)
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
