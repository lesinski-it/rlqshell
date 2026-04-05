"""Confirmation dialog shown before running a snippet."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from termplus.app.constants import Colors


class SnippetConfirmDialog(QDialog):
    """Preview the resolved script and confirm execution."""

    def __init__(
        self,
        snippet_name: str,
        script: str,
        target_info: str = "active terminal",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm Snippet Execution")
        self.setMinimumWidth(480)
        self.setMinimumHeight(260)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel(f"Run \u201c{snippet_name}\u201d?")
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        layout.addWidget(title)

        target_lbl = QLabel(f"Target: {target_info}")
        target_lbl.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_MUTED}; background: transparent;"
        )
        layout.addWidget(target_lbl)

        lbl = QLabel("Command to execute:")
        lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_SECONDARY}; "
            f"background: transparent;"
        )
        layout.addWidget(lbl)

        preview = QTextEdit()
        preview.setPlainText(script)
        preview.setReadOnly(True)
        preview.setStyleSheet(
            f"font-family: 'JetBrains Mono', monospace; font-size: 13px; "
            f"background-color: {Colors.BG_SURFACE}; color: {Colors.TEXT_PRIMARY}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 6px; padding: 8px;"
        )
        preview.setMinimumHeight(80)
        layout.addWidget(preview, 1)

        layout.addStretch()

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

        run_btn = QPushButton("Run")
        run_btn.setDefault(True)
        run_btn.setStyleSheet(
            f"background-color: {Colors.ACCENT}; color: #ffffff; "
            f"border: none; border-radius: 6px; "
            f"padding: 8px 20px; font-size: 13px; font-weight: 600;"
        )
        run_btn.clicked.connect(self.accept)
        btn_row.addWidget(run_btn)

        layout.addLayout(btn_row)

        self.setStyleSheet(f"QDialog {{ background-color: {Colors.BG_PRIMARY}; }}")
