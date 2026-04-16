"""Confirmation dialog shown before pasting multi-line text into a terminal."""

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

from rlqshell.app.constants import Colors


class PasteConfirmDialog(QDialog):
    """Preview multi-line clipboard content and confirm before pasting."""

    def __init__(
        self,
        text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Paste Confirmation")
        self.setMinimumWidth(500)
        self.setMinimumHeight(280)

        line_count = text.count("\n") + 1

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel(f"Paste {line_count} lines?")
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        layout.addWidget(title)

        warn_lbl = QLabel(
            "The clipboard contains multiple lines. "
            "Please review before pasting into the terminal."
        )
        warn_lbl.setWordWrap(True)
        warn_lbl.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_MUTED}; background: transparent;"
        )
        layout.addWidget(warn_lbl)

        preview = QTextEdit()
        preview.setPlainText(text)
        preview.setReadOnly(True)
        preview.setStyleSheet(
            f"font-family: 'JetBrains Mono', monospace; font-size: 13px; "
            f"background-color: {Colors.BG_SURFACE}; color: {Colors.TEXT_PRIMARY}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 6px; padding: 8px;"
        )
        preview.setMinimumHeight(100)
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

        paste_btn = QPushButton("Paste")
        paste_btn.setDefault(True)
        paste_btn.setStyleSheet(
            f"background-color: {Colors.ACCENT}; color: #ffffff; "
            f"border: none; border-radius: 6px; "
            f"padding: 8px 20px; font-size: 13px; font-weight: 600;"
        )
        paste_btn.clicked.connect(self.accept)
        btn_row.addWidget(paste_btn)

        layout.addLayout(btn_row)

        self.setStyleSheet(f"QDialog {{ background-color: {Colors.BG_PRIMARY}; }}")
