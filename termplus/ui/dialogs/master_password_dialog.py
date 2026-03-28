"""Master password dialog — unlock or set new master password at startup."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from termplus.app.constants import APP_NAME, Colors
from termplus.core.credential_store import CredentialStore


class MasterPasswordDialog(QDialog):
    """Modal dialog for unlocking or setting the master password.

    If vault.key exists → unlock mode (single password field).
    If vault.key does not exist → set-new mode (password + confirm).
    """

    def __init__(self, credential_store: CredentialStore, parent=None) -> None:
        super().__init__(parent)
        self._store = credential_store
        self._is_new = not credential_store.has_master_password

        self.setWindowTitle(f"{APP_NAME} — Hasło główne")
        self.setFixedSize(420, 280 if self._is_new else 260)
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

        # Title
        title = QLabel(
            "Ustaw hasło główne" if self._is_new else "Odblokuj sejf"
        )
        title.setObjectName("title")
        layout.addWidget(title)

        # Subtitle
        if self._is_new:
            subtitle = QLabel(
                "Wybierz hasło główne do ochrony danych sejfu.\n"
                "Po ustawieniu zostanie wygenerowany jednorazowy kod odzyskiwania."
            )
        else:
            subtitle = QLabel("Podaj hasło główne, aby odblokować sejf.")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Password field
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText("Hasło główne")
        self._password.returnPressed.connect(self._on_submit)
        layout.addWidget(self._password)

        # Confirm field (new password only)
        if self._is_new:
            self._confirm = QLineEdit()
            self._confirm.setEchoMode(QLineEdit.EchoMode.Password)
            self._confirm.setPlaceholderText("Potwierdź hasło")
            self._confirm.returnPressed.connect(self._on_submit)
            layout.addWidget(self._confirm)

        # Error label
        self._error_label = QLabel()
        self._error_label.setObjectName("error")
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

        # "Forgot password" link (unlock mode only)
        if not self._is_new:
            forgot_btn = QPushButton("Zapomniałem/am hasła — użyj kodu odzyskiwania")
            forgot_btn.setObjectName("forgotBtn")
            forgot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            forgot_btn.clicked.connect(self._on_forgot_password)
            layout.addWidget(forgot_btn)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._skip_btn = QPushButton("Pomiń")
        self._skip_btn.setObjectName("skipBtn")
        self._skip_btn.clicked.connect(self._on_skip)
        btn_row.addWidget(self._skip_btn)

        self._submit_btn = QPushButton(
            "Ustaw hasło" if self._is_new else "Odblokuj"
        )
        self._submit_btn.setObjectName("submitBtn")
        self._submit_btn.setDefault(True)
        self._submit_btn.clicked.connect(self._on_submit)
        btn_row.addWidget(self._submit_btn)

        layout.addLayout(btn_row)

        self._password.setFocus()

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
            QPushButton#skipBtn {{
                background-color: transparent;
                color: {Colors.TEXT_MUTED};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
            }}
            QPushButton#skipBtn:hover {{
                background-color: {Colors.BG_HOVER};
            }}
            QPushButton#forgotBtn {{
                background-color: transparent;
                color: {Colors.TEXT_MUTED};
                border: none;
                padding: 0px;
                font-size: 11px;
                text-align: left;
                text-decoration: underline;
            }}
            QPushButton#forgotBtn:hover {{
                color: {Colors.ACCENT};
            }}
        """)

    def _on_submit(self) -> None:
        password = self._password.text().strip()

        if not password:
            self._show_error("Hasło nie może być puste.")
            return

        if self._is_new:
            if len(password) < 6:
                self._show_error("Hasło musi mieć co najmniej 6 znaków.")
                return
            confirm = self._confirm.text().strip()
            if password != confirm:
                self._show_error("Hasła nie są zgodne.")
                return

            recovery_code = self._store.set_master_password(password)

            from termplus.ui.dialogs.recovery_code_dialog import RecoveryCodeDialog

            dlg = RecoveryCodeDialog(recovery_code, self)
            dlg.exec()
            self.accept()
        else:
            if self._store.unlock(password):
                self.accept()
            else:
                self._show_error("Błędne hasło. Spróbuj ponownie.")
                self._password.selectAll()
                self._password.setFocus()

    def _on_forgot_password(self) -> None:
        if not self._store.has_recovery:
            QMessageBox.information(
                self,
                "Odzyskiwanie niedostępne",
                "Ten sejf nie ma zapisanego kodu odzyskiwania.\n\n"
                "Kod odzyskiwania jest generowany przy ustawieniu lub zmianie\n"
                "hasła w nowszej wersji aplikacji. Nie możesz odzyskać dostępu\n"
                "bez znajomości hasła głównego.",
            )
            return

        from termplus.ui.dialogs.recover_vault_dialog import RecoverVaultDialog

        dlg = RecoverVaultDialog(self._store, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.accept()

    def _on_skip(self) -> None:
        if self._is_new:
            self.reject()
        else:
            reply = QMessageBox.warning(
                self,
                "Pomiń odblokowanie",
                "Bez odblokowania zaszyfrowane dane uwierzytelniające\n"
                "nie będą dostępne. Połączenia kluczem SSH nadal działają.\n\n"
                "Kontynuować bez odblokowania?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.reject()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(True)
