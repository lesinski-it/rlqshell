"""Identity editor dialog — placeholder for Stage 5 credential integration."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from termplus.app.constants import Colors


class IdentityEditor(QDialog):
    """Dialog for creating/editing an identity (username + auth method).

    Full credential encryption integrated in Stage 5.
    """

    identity_saved = Signal(int)  # identity_id

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Identity")
        self.setFixedSize(400, 320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        layout.addWidget(self._make_label("Label"))
        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("e.g. admin@prod")
        layout.addWidget(self._label_edit)

        layout.addWidget(self._make_label("Username"))
        self._username_edit = QLineEdit()
        self._username_edit.setPlaceholderText("e.g. admin")
        layout.addWidget(self._username_edit)

        layout.addWidget(self._make_label("Auth Type"))
        self._auth_combo = QComboBox()
        self._auth_combo.addItems(["password", "key", "key+passphrase", "agent"])
        layout.addWidget(self._auth_combo)

        layout.addWidget(self._make_label("Password"))
        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setPlaceholderText("Enter password")
        layout.addWidget(self._password_edit)

        layout.addStretch()

        save_btn = QPushButton("Save")
        save_btn.setProperty("cssClass", "primary")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_SECONDARY}; "
            f"background: transparent;"
        )
        return lbl

    def _save(self) -> None:
        # Placeholder — real save in Stage 5 with CredentialStore
        self.accept()
