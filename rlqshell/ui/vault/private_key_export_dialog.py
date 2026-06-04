"""Private key export dialog — master password gate then file save."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import Colors
from rlqshell.core.credential_store import CredentialStore
from rlqshell.core.keychain import Keychain
from rlqshell.core.models.ssh_key import SSHKey

logger = logging.getLogger(__name__)

_DEFAULT_NAMES: dict[str, str] = {
    "ed25519": "id_ed25519",
    "rsa": "id_rsa",
    "ecdsa": "id_ecdsa",
}


class PrivateKeyExportDialog(QDialog):
    """Two-phase dialog: confirm master password, then save private key to file.

    Phase 1 — re-authentication: user enters master password.
    Phase 2 — export: save PEM bytes to a user-selected file.
    """

    def __init__(
        self,
        credential_store: CredentialStore,
        keychain: Keychain,
        key: SSHKey,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = credential_store
        self._keychain = keychain
        self._key = key
        self._pem: bytes | None = None

        self.setWindowTitle("Eksportuj klucz prywatny")
        self.setFixedSize(440, 320)
        self.setModal(True)

        self._stack = QStackedWidget()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._stack)

        self._stack.addWidget(self._build_phase1())
        self._stack.addWidget(self._build_phase2())

        self._apply_style()

    # ------------------------------------------------------------------
    # Phase 1 — master password confirmation
    # ------------------------------------------------------------------

    def _build_phase1(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        layout.addWidget(self._context_header())

        desc = QLabel("Podaj hasło główne, aby wyeksportować klucz prywatny.")
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        layout.addWidget(desc)

        layout.addWidget(self._field_label("Hasło główne"))
        self._master_pwd_edit = QLineEdit()
        self._master_pwd_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._master_pwd_edit.setPlaceholderText("Wprowadź hasło główne")
        self._master_pwd_edit.returnPressed.connect(self._confirm)
        layout.addWidget(self._master_pwd_edit)

        self._error_label = QLabel()
        self._error_label.setStyleSheet(
            f"color: {Colors.DANGER}; font-size: 12px; background: transparent;"
        )
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Anuluj")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        confirm_btn = QPushButton("Potwierdź")
        confirm_btn.setObjectName("primaryBtn")
        confirm_btn.setDefault(True)
        confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm_btn.clicked.connect(self._confirm)
        btn_row.addWidget(confirm_btn)
        layout.addLayout(btn_row)

        return page

    # ------------------------------------------------------------------
    # Phase 2 — export
    # ------------------------------------------------------------------

    def _build_phase2(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        layout.addWidget(self._context_header())

        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        self._status_label.setVisible(False)
        layout.addWidget(self._status_label)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Zamknij")
        close_btn.setObjectName("cancelBtn")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        self._save_btn = QPushButton("Zapisz do pliku")
        self._save_btn.setObjectName("primaryBtn")
        self._save_btn.setDefault(True)
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.clicked.connect(self._save_to_file)
        btn_row.addWidget(self._save_btn)
        layout.addLayout(btn_row)

        return page

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _context_header(self) -> QWidget:
        container = QWidget()
        container.setStyleSheet(
            f"background-color: {Colors.BG_SURFACE}; border-radius: 6px;"
        )
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        lbl = QLabel(self._key.label or "Unnamed key")
        lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {Colors.TEXT_PRIMARY};"
            f" background: transparent;"
        )
        layout.addWidget(lbl)

        fp = self._key.fingerprint or ""
        if len(fp) > 50:
            fp = fp[:50] + "..."
        fp_label = QLabel(f"{self._key.key_type.upper()}  ·  {fp}")
        fp_label.setStyleSheet(
            f"font-size: 11px; color: {Colors.TEXT_MUTED}; background: transparent;"
            f" font-family: 'JetBrains Mono', monospace;"
        )
        layout.addWidget(fp_label)

        return container

    def _field_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_SECONDARY};"
            f" background: transparent;"
        )
        return lbl

    def _confirm(self) -> None:
        entered = self._master_pwd_edit.text()
        if not entered:
            self._show_error("Podaj hasło główne.")
            return

        if not self._store.unlock(entered):
            self._show_error("Nieprawidłowe hasło główne.")
            self._master_pwd_edit.clear()
            self._master_pwd_edit.setFocus()
            return

        self._pem = self._keychain.export_private_key(self._key.id)
        self._master_pwd_edit.clear()

        if self._pem is None:
            self._show_error("Nie można odczytać klucza — brak danych.")
            return

        self._stack.setCurrentIndex(1)

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._error_label.setVisible(True)

    def _save_to_file(self) -> None:
        if self._pem is None:
            return

        default_name = _DEFAULT_NAMES.get(self._key.key_type, "id_key")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Eksportuj klucz prywatny",
            default_name,
            "All Files (*)",
        )
        if not file_path:
            return

        try:
            with open(file_path, "wb") as f:
                f.write(self._pem)
            self._status_label.setText(f"Zapisano: {file_path}")
            self._status_label.setStyleSheet(
                f"font-size: 12px; color: {Colors.SUCCESS}; background: transparent;"
            )
            self._status_label.setVisible(True)
            self._save_btn.setEnabled(False)
            logger.info("Private key %d exported to %s", self._key.id, file_path)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Błąd zapisu",
                f"Nie można zapisać klucza:\n{exc}",
            )

    def done(self, result: int) -> None:
        self._pem = None
        super().done(result)

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Colors.BG_PRIMARY};
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
            QPushButton#primaryBtn {{
                background-color: {Colors.ACCENT};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton#primaryBtn:hover {{
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
