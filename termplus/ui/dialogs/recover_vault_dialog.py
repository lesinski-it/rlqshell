"""Recover vault dialog — regain access using a recovery code."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from termplus.app.constants import APP_NAME, Colors
from termplus.core.credential_store import CredentialStore


class RecoverVaultDialog(QDialog):
    """Modal dialog to recover vault access using a recovery code.

    The user provides their saved recovery code and sets a new master password.
    All vault data is re-encrypted with the new password and a new recovery code
    is generated and displayed.
    """

    def __init__(self, credential_store: CredentialStore, parent=None) -> None:
        super().__init__(parent)
        self._store = credential_store

        self.setWindowTitle(f"{APP_NAME} — Recover Access")
        self.setFixedSize(440, 330)
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
        layout.setSpacing(14)

        title = QLabel("Recover Vault Access")
        title.setObjectName("title")
        layout.addWidget(title)

        subtitle = QLabel(
            "Enter your saved recovery code and set a new password.\n"
            "All data will be preserved."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self._code_field = QLineEdit()
        self._code_field.setPlaceholderText("Recovery code (XXXXX-XXXXX-XXXXX-XXXXX-XXXXX)")
        self._code_field.returnPressed.connect(self._on_submit)
        layout.addWidget(self._code_field)

        self._new_pass = QLineEdit()
        self._new_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._new_pass.setPlaceholderText("New password (min. 6 characters)")
        self._new_pass.returnPressed.connect(self._on_submit)
        layout.addWidget(self._new_pass)

        self._confirm = QLineEdit()
        self._confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm.setPlaceholderText("Confirm new password")
        self._confirm.returnPressed.connect(self._on_submit)
        layout.addWidget(self._confirm)

        self._error_label = QLabel()
        self._error_label.setObjectName("error")
        self._error_label.setVisible(False)
        self._error_label.setWordWrap(True)
        layout.addWidget(self._error_label)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._submit_btn = QPushButton("Recover Access")
        self._submit_btn.setObjectName("submitBtn")
        self._submit_btn.setDefault(True)
        self._submit_btn.clicked.connect(self._on_submit)
        btn_row.addWidget(self._submit_btn)

        layout.addLayout(btn_row)

        self._code_field.setFocus()

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
            QLabel#error {{
                color: {Colors.DANGER};
                font-size: 12px;
            }}
            QLineEdit {{
                background-color: {Colors.BG_SURFACE};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {Colors.ACCENT};
            }}
            QPushButton#submitBtn {{
                background-color: {Colors.ACCENT};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton#submitBtn:hover {{
                background-color: {Colors.ACCENT_HOVER};
            }}
            QPushButton#cancelBtn {{
                background-color: transparent;
                color: {Colors.TEXT_MUTED};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
            }}
            QPushButton#cancelBtn:hover {{
                background-color: {Colors.BG_HOVER};
            }}
        """)

    def _on_submit(self) -> None:
        code = self._code_field.text().strip()
        new_pass = self._new_pass.text()
        confirm = self._confirm.text()

        if not code:
            self._show_error("Enter the recovery code.")
            return
        if len(new_pass) < 6:
            self._show_error("New password must be at least 6 characters.")
            return
        if new_pass != confirm:
            self._show_error("Passwords do not match.")
            return

        self._submit_btn.setEnabled(False)
        self._submit_btn.setText("Recovering…")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            recovery_code = self._store.recover_with_code(code, new_pass)
        except Exception as exc:
            self._show_error(str(exc) or type(exc).__name__)
            self._submit_btn.setEnabled(True)
            self._submit_btn.setText("Recover Access")
            self._code_field.selectAll()
            self._code_field.setFocus()
            return

        from termplus.ui.dialogs.recovery_code_dialog import RecoveryCodeDialog

        dlg = RecoveryCodeDialog(recovery_code, self)
        dlg.exec()
        self.accept()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(True)
