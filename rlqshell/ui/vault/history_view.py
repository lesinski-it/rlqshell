"""History view — table of recent connection history."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import Colors
from rlqshell.core.history_manager import HistoryManager

logger = logging.getLogger(__name__)


class HistoryView(QWidget):
    """Connection history table with search and clear."""

    def __init__(
        self,
        history_manager: HistoryManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._manager = history_manager

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

        title = QLabel("Connection History")
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        tb.addWidget(title)
        tb.addStretch()

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter…")
        self._search.setFixedWidth(200)
        self._search.setProperty("cssClass", "search")
        self._search.textChanged.connect(lambda: self.refresh())
        tb.addWidget(self._search)

        clear_btn = QPushButton("Clear History")
        clear_btn.setStyleSheet(
            f"background: transparent; color: {Colors.DANGER}; border: 1px solid {Colors.DANGER}; "
            f"border-radius: 6px; padding: 6px 12px; font-size: 12px;"
        )
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.clicked.connect(self._on_clear)
        tb.addWidget(clear_btn)

        layout.addWidget(toolbar)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["Host", "Address", "Protocol", "Connected", "Duration"]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {Colors.BG_PRIMARY};
                color: {Colors.TEXT_PRIMARY};
                border: none;
                gridline-color: {Colors.BORDER};
                font-size: 12px;
            }}
            QTableWidget::item {{
                padding: 6px 8px;
            }}
            QTableWidget::item:selected {{
                background-color: {Colors.BG_SURFACE};
            }}
            QHeaderView::section {{
                background-color: {Colors.BG_DARKER};
                color: {Colors.TEXT_SECONDARY};
                font-weight: 600;
                font-size: 11px;
                padding: 6px 8px;
                border: none;
                border-bottom: 1px solid {Colors.BORDER};
            }}
        """)
        layout.addWidget(self._table)

        self.refresh()

    def refresh(self) -> None:
        search = self._search.text().strip() or None
        records = self._manager.list_connections(search=search)

        self._table.setRowCount(len(records))
        for i, rec in enumerate(records):
            self._table.setItem(i, 0, QTableWidgetItem(rec.host_label))
            self._table.setItem(i, 1, QTableWidgetItem(rec.address))
            self._table.setItem(i, 2, QTableWidgetItem(rec.protocol.upper()))
            self._table.setItem(i, 3, QTableWidgetItem(rec.connected_at or ""))
            duration = self._format_duration(rec.duration_seconds)
            self._table.setItem(i, 4, QTableWidgetItem(duration))

    @staticmethod
    def _format_duration(seconds: int | None) -> str:
        if seconds is None:
            return "active"
        if seconds < 60:
            return f"{seconds}s"
        if seconds < 3600:
            return f"{seconds // 60}m {seconds % 60}s"
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}m"

    def _on_clear(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self, "Clear History",
            "Are you sure you want to clear all connection history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._manager.clear_history()
            self.refresh()
