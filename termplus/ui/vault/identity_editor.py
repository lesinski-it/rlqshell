"""Identity editor dialog — create/edit identities with CredentialStore."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from termplus.app.constants import Colors
from termplus.core.credential_store import CredentialStore
from termplus.core.keychain import Keychain


class IdentityEditor(QDialog):
    """Dialog for creating/editing an identity (username + auth method).

    Saves credentials via CredentialStore with encrypted password.
    """

    identity_saved = Signal(int)  # identity_id

    def __init__(
        self,
        credential_store: CredentialStore,
        keychain: Keychain,
        parent: QWidget | None = None,
        identity_id: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = credential_store
        self._keychain = keychain
        self._identity_id = identity_id

        self.setWindowTitle("Edit Identity" if identity_id else "New Identity")
        self.setFixedSize(420, 380)

        self._build_ui()
        self._apply_style()
        self._on_auth_type_changed()

        if identity_id:
            self._load_identity(identity_id)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # Label
        layout.addWidget(self._make_label("Label"))
        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("e.g. admin@prod")
        layout.addWidget(self._label_edit)

        # Username
        layout.addWidget(self._make_label("Username"))
        self._username_edit = QLineEdit()
        self._username_edit.setPlaceholderText("e.g. admin")
        layout.addWidget(self._username_edit)

        # Auth Type
        layout.addWidget(self._make_label("Auth Type"))
        self._auth_combo = QComboBox()
        self._auth_combo.addItems(["password", "key", "key+passphrase", "agent"])
        self._auth_combo.currentIndexChanged.connect(self._on_auth_type_changed)
        layout.addWidget(self._auth_combo)

        # Password field
        self._password_label = self._make_label("Password")
        layout.addWidget(self._password_label)
        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setPlaceholderText("Enter password")
        layout.addWidget(self._password_edit)

        # SSH Key dropdown
        self._key_label = self._make_label("SSH Key")
        layout.addWidget(self._key_label)
        self._key_combo = QComboBox()
        self._populate_keys()
        layout.addWidget(self._key_combo)

        # Error label
        self._error_label = QLabel()
        self._error_label.setStyleSheet(f"color: {Colors.DANGER}; font-size: 12px; background: transparent;")
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("saveBtn")
        save_btn.setDefault(True)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def _populate_keys(self) -> None:
        self._key_combo.clear()
        self._key_combo.addItem("— None —", None)
        for key in self._keychain.list_keys():
            display = f"{key.label or 'Unnamed'} ({key.key_type})"
            self._key_combo.addItem(display, key.id)

    def _on_auth_type_changed(self) -> None:
        auth = self._auth_combo.currentText()
        show_password = auth in ("password", "key+passphrase")
        show_key = auth in ("key", "key+passphrase")

        self._password_label.setVisible(show_password)
        self._password_edit.setVisible(show_password)
        self._key_label.setVisible(show_key)
        self._key_combo.setVisible(show_key)

        if auth == "key+passphrase":
            self._password_label.setText("Passphrase")
            self._password_edit.setPlaceholderText("Key passphrase")
        else:
            self._password_label.setText("Password")
            self._password_edit.setPlaceholderText("Enter password")

    def _load_identity(self, identity_id: int) -> None:
        identity = self._store.get_identity(identity_id)
        if identity is None:
            return
        self._label_edit.setText(identity.label)
        self._username_edit.setText(identity.username)

        idx = self._auth_combo.findText(identity.auth_type)
        if idx >= 0:
            self._auth_combo.setCurrentIndex(idx)

        if identity.ssh_key_id:
            key_idx = self._key_combo.findData(identity.ssh_key_id)
            if key_idx >= 0:
                self._key_combo.setCurrentIndex(key_idx)

    def _save(self) -> None:
        label = self._label_edit.text().strip()
        username = self._username_edit.text().strip()
        auth_type = self._auth_combo.currentText()

        if not label:
            self._show_error("Label is required.")
            return
        if not username:
            self._show_error("Username is required.")
            return

        password = None
        if auth_type in ("password", "key+passphrase"):
            password = self._password_edit.text()
            if not password and not self._identity_id:
                self._show_error("Password is required.")
                return

        ssh_key_id = None
        if auth_type in ("key", "key+passphrase"):
            ssh_key_id = self._key_combo.currentData()
            if ssh_key_id is None:
                self._show_error("Select an SSH key.")
                return

        if self._identity_id:
            # Update — delete old and re-create (simple approach)
            self._store.delete_identity(self._identity_id)

        identity_id = self._store.create_identity(
            label=label,
            username=username,
            auth_type=auth_type,
            password=password if password else None,
            ssh_key_id=ssh_key_id,
        )

        self.identity_saved.emit(identity_id)
        self.accept()

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._error_label.setVisible(True)

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_SECONDARY}; "
            f"background: transparent;"
        )
        return lbl

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Colors.BG_PRIMARY};
            }}
            QLineEdit, QComboBox {{
                background-color: {Colors.BG_SURFACE};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }}
            QLineEdit:focus, QComboBox:focus {{
                border-color: {Colors.ACCENT};
            }}
            QComboBox::drop-down {{
                border: none;
                padding-right: 8px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {Colors.BG_SURFACE};
                color: {Colors.TEXT_PRIMARY};
                selection-background-color: {Colors.ACCENT};
                border: 1px solid {Colors.BORDER};
            }}
            QPushButton#saveBtn {{
                background-color: {Colors.ACCENT};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton#saveBtn:hover {{
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
