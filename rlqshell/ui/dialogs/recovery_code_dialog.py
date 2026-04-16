"""Recovery code dialog — display the one-time recovery code to the user."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QClipboard, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from rlqshell.app.constants import APP_NAME, Colors


class RecoveryCodeDialog(QDialog):
    """Modal dialog that shows the recovery code once after setting/changing the password.

    The dialog cannot be closed until the user confirms they have saved the code.
    """

    def __init__(self, recovery_code: str, parent=None) -> None:
        super().__init__(parent)
        self._code = recovery_code

        self.setWindowTitle(f"{APP_NAME} — Recovery Code")
        self.setFixedSize(460, 340)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.CustomizeWindowHint
        )

        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(16)

        title = QLabel("Save Your Recovery Code")
        title.setObjectName("title")
        layout.addWidget(title)

        subtitle = QLabel(
            "This code will only be shown once. Without it, you will not\n"
            "be able to recover vault data if you lose your master password."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Code display
        code_label = QLabel(self._code)
        code_label.setObjectName("code")
        code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        code_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(code_label)

        # Copy button
        copy_btn = QPushButton("Copy to clipboard")
        copy_btn.setObjectName("copyBtn")
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.clicked.connect(self._on_copy)
        layout.addWidget(copy_btn, alignment=Qt.AlignmentFlag.AlignHCenter)

        layout.addSpacing(4)

        # Confirmation checkbox
        self._checkbox = QCheckBox("I have saved the code in a safe place")
        self._checkbox.setObjectName("confirmCheck")
        self._checkbox.toggled.connect(self._on_checkbox_toggled)
        layout.addWidget(self._checkbox)

        layout.addStretch()

        # OK button (disabled until checkbox checked)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._ok_btn = QPushButton("OK")
        self._ok_btn.setObjectName("okBtn")
        self._ok_btn.setEnabled(False)
        self._ok_btn.setDefault(True)
        self._ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._ok_btn)
        layout.addLayout(btn_row)

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Colors.BG_PRIMARY};
            }}
            QLabel#title {{
                color: {Colors.TEXT_PRIMARY};
                font-size: 18px;
                font-weight: 700;
            }}
            QLabel#subtitle {{
                color: {Colors.TEXT_SECONDARY};
                font-size: 12px;
            }}
            QLabel#code {{
                color: {Colors.TEXT_PRIMARY};
                background-color: {Colors.BG_SURFACE};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                font-family: 'JetBrains Mono', 'Consolas', monospace;
                font-size: 16px;
                font-weight: 700;
                letter-spacing: 2px;
                padding: 14px 20px;
            }}
            QPushButton#copyBtn {{
                background-color: transparent;
                color: {Colors.ACCENT};
                border: 1px solid {Colors.ACCENT};
                border-radius: 6px;
                padding: 6px 18px;
                font-size: 12px;
            }}
            QPushButton#copyBtn:hover {{
                background-color: {Colors.BG_HOVER};
            }}
            QCheckBox#confirmCheck {{
                color: {Colors.TEXT_SECONDARY};
                font-size: 12px;
            }}
            QCheckBox#confirmCheck::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {Colors.BORDER};
                border-radius: 3px;
                background-color: {Colors.BG_SURFACE};
            }}
            QCheckBox#confirmCheck::indicator:checked {{
                background-color: {Colors.ACCENT};
                border-color: {Colors.ACCENT};
            }}
            QPushButton#okBtn {{
                background-color: {Colors.ACCENT};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 28px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton#okBtn:hover {{
                background-color: {Colors.ACCENT_HOVER};
            }}
            QPushButton#okBtn:disabled {{
                background-color: {Colors.BG_SURFACE};
                color: {Colors.TEXT_MUTED};
            }}
        """)

    def _on_copy(self) -> None:
        clipboard: QClipboard = QGuiApplication.clipboard()
        clipboard.setText(self._code)

    def _on_checkbox_toggled(self, checked: bool) -> None:
        self._ok_btn.setEnabled(checked)

    def closeEvent(self, event) -> None:
        if not self._checkbox.isChecked():
            event.ignore()
        else:
            super().closeEvent(event)
