"""RDP credentials dialog — prompt for username/password before connecting."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from termplus.app.constants import Colors

if __import__("typing").TYPE_CHECKING:
    from termplus.core.credential_store import CredentialStore


class RDPCredentialsDialog(QDialog):
    """Modal dialog asking for RDP credentials when not stored in vault."""

    def __init__(
        self,
        hostname: str = "",
        username: str = "",
        domain: str = "",
        credential_store: CredentialStore | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._credential_store = credential_store

        self.setWindowTitle("RDP Credentials")
        self.setFixedSize(400, 400)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(10)

        title = QLabel(f"Connect to {hostname}")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {Colors.TEXT_PRIMARY};"
        )
        layout.addWidget(title)

        subtitle = QLabel("Enter your Windows credentials:")
        subtitle.setStyleSheet(f"font-size: 12px; color: {Colors.TEXT_MUTED};")
        layout.addWidget(subtitle)

        # Saved identity picker
        self._identity_combo: QComboBox | None = None
        if credential_store and credential_store.is_unlocked:
            identities = credential_store.list_identities()
            # Only show picker when there are identities with passwords
            pwd_identities = [
                i for i in identities if i.encrypted_password
            ]
            if pwd_identities:
                lbl = QLabel("Saved identity")
                lbl.setStyleSheet(
                    f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_SECONDARY};"
                )
                layout.addWidget(lbl)
                self._identity_combo = QComboBox()
                self._identity_combo.addItem("— Manual entry —", None)
                for ident in pwd_identities:
                    display = f"{ident.label} ({ident.username})"
                    self._identity_combo.addItem(display, ident.id)
                self._identity_combo.currentIndexChanged.connect(
                    self._on_identity_selected,
                )
                layout.addWidget(self._identity_combo)

        # Username
        lbl = QLabel("Username")
        lbl.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_SECONDARY};")
        layout.addWidget(lbl)
        self._username_edit = QLineEdit()
        self._username_edit.setText(username)
        self._username_edit.setPlaceholderText("e.g. Administrator")
        layout.addWidget(self._username_edit)

        # Domain
        lbl = QLabel("Domain (optional)")
        lbl.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_SECONDARY};")
        layout.addWidget(lbl)
        self._domain_edit = QLineEdit()
        self._domain_edit.setText(domain)
        self._domain_edit.setPlaceholderText("e.g. CORP")
        layout.addWidget(self._domain_edit)

        # Password
        lbl = QLabel("Password")
        lbl.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_SECONDARY};")
        layout.addWidget(lbl)
        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setPlaceholderText("Password")
        layout.addWidget(self._password_edit)

        # Validation error label (hidden by default)
        self._error_label = QLabel("")
        self._error_label.setStyleSheet(
            f"font-size: 11px; color: {Colors.DANGER}; padding: 0;"
        )
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        layout.addStretch()

        # Connect button
        connect_btn = QPushButton("Connect")
        connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        connect_btn.setStyleSheet(
            f"QPushButton {{ background-color: {Colors.ACCENT}; color: #fff; "
            f"border: none; border-radius: 6px; padding: 8px 16px; font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: {Colors.ACCENT_HOVER}; }}"
        )
        connect_btn.clicked.connect(self._validate_and_accept)
        layout.addWidget(connect_btn)

        self._password_edit.returnPressed.connect(self._validate_and_accept)

        self.setStyleSheet(
            f"QDialog {{ background-color: {Colors.BG_PRIMARY}; }}"
            f"QLineEdit {{ background-color: {Colors.BG_SURFACE}; color: {Colors.TEXT_PRIMARY}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 4px; padding: 6px 10px; }}"
            f"QComboBox {{ background-color: {Colors.BG_SURFACE}; color: {Colors.TEXT_PRIMARY}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 4px; padding: 6px 10px; }}"
            f"QComboBox::drop-down {{ border: none; }}"
            f"QComboBox QAbstractItemView {{ background-color: {Colors.BG_SURFACE}; "
            f"color: {Colors.TEXT_PRIMARY}; selection-background-color: {Colors.ACCENT}; }}"
        )

        # Focus first empty field
        if username:
            self._password_edit.setFocus()
        else:
            self._username_edit.setFocus()

    # ------------------------------------------------------------------
    # Identity picker
    # ------------------------------------------------------------------

    def _on_identity_selected(self) -> None:
        """Fill username & password from the selected vault identity."""
        if self._identity_combo is None or self._credential_store is None:
            return
        identity_id = self._identity_combo.currentData()
        if identity_id is None:
            # "Manual entry" selected — clear fields for manual input
            self._username_edit.clear()
            self._password_edit.clear()
            self._username_edit.setReadOnly(False)
            self._password_edit.setReadOnly(False)
            self._username_edit.setFocus()
            return

        identity = self._credential_store.get_identity(identity_id)
        if identity is None:
            return

        self._username_edit.setText(identity.username)
        self._username_edit.setReadOnly(True)

        try:
            pwd = self._credential_store.get_decrypted_password(identity_id)
            self._password_edit.setText(pwd or "")
            self._password_edit.setReadOnly(True)
        except Exception:
            self._password_edit.clear()
            self._password_edit.setReadOnly(False)
            self._password_edit.setFocus()

        self._error_label.hide()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_and_accept(self) -> None:
        """Validate fields before accepting the dialog."""
        username = self._username_edit.text().strip()
        password = self._password_edit.text()
        errors: list[str] = []
        if not username:
            errors.append("Username is required.")
        if not password:
            errors.append("Password is required.")
        if errors:
            self._error_label.setText(" ".join(errors))
            self._error_label.show()
            if not username:
                self._username_edit.setFocus()
            else:
                self._password_edit.setFocus()
            return
        self._error_label.hide()
        self.accept()

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def username(self) -> str:
        return self._username_edit.text()

    def password(self) -> str:
        return self._password_edit.text()

    def domain(self) -> str:
        return self._domain_edit.text()
