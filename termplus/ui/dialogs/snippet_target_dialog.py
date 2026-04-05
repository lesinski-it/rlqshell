"""Dialog for selecting which terminals to broadcast a snippet to."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from termplus.app.constants import Colors


class SnippetTargetDialog(QDialog):
    """Let the user pick which terminal sessions to send a snippet to."""

    def __init__(
        self,
        sessions: list[tuple[str, str]],
        parent: QWidget | None = None,
    ) -> None:
        """*sessions*: list of ``(tab_id, label)``."""
        super().__init__(parent)
        self.setWindowTitle("Select Terminals")
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)

        self._checkboxes: list[tuple[str, QCheckBox]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        header = QLabel("Send snippet to:")
        header.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        layout.addWidget(header)

        # Select All / Deselect All
        sel_row = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.setStyleSheet(
            f"background: transparent; color: {Colors.ACCENT}; border: none; "
            f"font-size: 12px; font-weight: 600; padding: 4px 8px;"
        )
        select_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        select_all_btn.clicked.connect(lambda: self._set_all(True))
        sel_row.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; border: none; "
            f"font-size: 12px; padding: 4px 8px;"
        )
        deselect_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        deselect_all_btn.clicked.connect(lambda: self._set_all(False))
        sel_row.addWidget(deselect_all_btn)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        # Session checkboxes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {Colors.BORDER}; border-radius: 6px; "
            f"background-color: {Colors.BG_SURFACE}; }}"
        )
        container = QWidget()
        container.setStyleSheet(f"background: transparent;")
        cl = QVBoxLayout(container)
        cl.setContentsMargins(12, 8, 12, 8)
        cl.setSpacing(6)

        for tab_id, label in sessions:
            cb = QCheckBox(label)
            cb.setChecked(True)
            cb.setStyleSheet(
                f"color: {Colors.TEXT_PRIMARY}; font-size: 13px; background: transparent;"
            )
            cl.addWidget(cb)
            self._checkboxes.append((tab_id, cb))

        cl.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 6px; "
            f"padding: 8px 16px; font-size: 13px;"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        send_btn = QPushButton("Send")
        send_btn.setDefault(True)
        send_btn.setStyleSheet(
            f"background-color: {Colors.ACCENT}; color: #ffffff; "
            f"border: none; border-radius: 6px; "
            f"padding: 8px 20px; font-size: 13px; font-weight: 600;"
        )
        send_btn.clicked.connect(self.accept)
        btn_row.addWidget(send_btn)

        layout.addLayout(btn_row)

        self.setStyleSheet(f"QDialog {{ background-color: {Colors.BG_PRIMARY}; }}")

    def _set_all(self, checked: bool) -> None:
        for _, cb in self._checkboxes:
            cb.setChecked(checked)

    @property
    def selected_tab_ids(self) -> list[str]:
        return [tid for tid, cb in self._checkboxes if cb.isChecked()]
