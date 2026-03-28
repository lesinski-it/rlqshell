"""Change master password dialog — verify old password and set a new one."""

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


class ChangeMasterPasswordDialog(QDialog):
    """Modal dialog for changing the master password.

    Verifies the current password, then re-encrypts all vault data with
    the new password and shows a new recovery code.
    """

    def __init__(self, credential_store: CredentialStore, parent=None) -> None:
        super().__init__(parent)
        self._store = credential_store

        self.setWindowTitle(f"{APP_NAME} — Zmień hasło główne")
        self.setFixedSize(440, 320)
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

        title = QLabel("Zmień hasło główne")
        title.setObjectName("title")
        layout.addWidget(title)

        subtitle = QLabel(
            "Po zmianie zostanie wygenerowany nowy kod odzyskiwania.\n"
            "Wszystkie dane zostaną ponownie zaszyfrowane."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self._current = QLineEdit()
        self._current.setEchoMode(QLineEdit.EchoMode.Password)
        self._current.setPlaceholderText("Obecne hasło")
        self._current.returnPressed.connect(self._on_submit)
        layout.addWidget(self._current)

        self._new_pass = QLineEdit()
        self._new_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._new_pass.setPlaceholderText("Nowe hasło (min. 6 znaków)")
        self._new_pass.returnPressed.connect(self._on_submit)
        layout.addWidget(self._new_pass)

        self._confirm = QLineEdit()
        self._confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm.setPlaceholderText("Potwierdź nowe hasło")
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

        cancel_btn = QPushButton("Anuluj")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._submit_btn = QPushButton("Zmień hasło")
        self._submit_btn.setObjectName("submitBtn")
        self._submit_btn.setDefault(True)
        self._submit_btn.clicked.connect(self._on_submit)
        btn_row.addWidget(self._submit_btn)

        layout.addLayout(btn_row)

        self._current.setFocus()

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
        current = self._current.text()
        new_pass = self._new_pass.text()
        confirm = self._confirm.text()

        if not current:
            self._show_error("Podaj obecne hasło.")
            return
        if len(new_pass) < 6:
            self._show_error("Nowe hasło musi mieć co najmniej 6 znaków.")
            return
        if new_pass != confirm:
            self._show_error("Nowe hasła nie są zgodne.")
            return

        self._submit_btn.setEnabled(False)
        self._submit_btn.setText("Zmieniam…")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            recovery_code = self._store.change_master_password(current, new_pass)
        except Exception as exc:
            self._show_error(str(exc) or type(exc).__name__)
            self._submit_btn.setEnabled(True)
            self._submit_btn.setText("Zmień hasło")
            self._current.selectAll()
            self._current.setFocus()
            return

        from termplus.ui.dialogs.recovery_code_dialog import RecoveryCodeDialog

        dlg = RecoveryCodeDialog(recovery_code, self)
        dlg.exec()
        self.accept()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(True)
