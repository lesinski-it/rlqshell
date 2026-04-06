"""Known hosts view — table of stored server fingerprints."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from termplus.app.constants import Colors
from termplus.core.known_hosts import KnownHostsManager
from termplus.ui.widgets.empty_state import EmptyState

logger = logging.getLogger(__name__)


class KnownHostsView(QWidget):
    """Table view for managing known SSH hosts."""

    def __init__(self, manager: KnownHostsManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._manager = manager

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setFixedHeight(52)
        toolbar.setStyleSheet(
            f"background-color: {Colors.BG_PRIMARY}; "
            f"border-bottom: 1px solid {Colors.BORDER};"
        )
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(16, 8, 16, 8)

        title = QLabel("Known Hosts")
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        tb_layout.addWidget(title)
        tb_layout.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh)
        tb_layout.addWidget(refresh_btn)

        layout.addWidget(toolbar)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["Hostname", "Port", "Key Type", "Fingerprint", ""]
        )
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(4, 90)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(48)
        layout.addWidget(self._table)

        # Empty state
        self._empty_state = EmptyState(
            title="No Known Hosts",
            description="Host keys will appear here after your first SSH connection.",
            icon_text="🔐",
        )
        layout.addWidget(self._empty_state)

        self.refresh()

    def refresh(self) -> None:
        entries = self._manager.list_all()

        if not entries:
            self._table.setVisible(False)
            self._empty_state.setVisible(True)
            return

        self._table.setVisible(True)
        self._empty_state.setVisible(False)
        self._table.setRowCount(len(entries))

        for row, entry in enumerate(entries):
            self._table.setItem(row, 0, QTableWidgetItem(entry.get("hostname", "")))
            self._table.setItem(row, 1, QTableWidgetItem(str(entry.get("port", 22))))
            self._table.setItem(row, 2, QTableWidgetItem(entry.get("key_type", "")))

            fp = entry.get("fingerprint", "")
            if len(fp) > 40:
                fp = fp[:40] + "..."
            self._table.setItem(row, 3, QTableWidgetItem(fp))

            # Delete button
            del_btn = QPushButton("Delete")
            del_btn.setProperty("cssClass", "danger")
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            entry_id = entry.get("id", 0)
            del_btn.clicked.connect(lambda checked=False, eid=entry_id: self._delete(eid))
            self._table.setCellWidget(row, 4, del_btn)

    def _delete(self, entry_id: int) -> None:
        reply = QMessageBox.question(
            self, "Delete Known Host",
            "Remove this host key? You will be prompted to verify it again on next connection.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._manager.delete_by_id(entry_id)
            self.refresh()
