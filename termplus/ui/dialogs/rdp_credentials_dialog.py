"""RDP credentials dialog — prompt for username/password before connecting."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from termplus.app.constants import Colors


class RDPCredentialsDialog(QDialog):
    """Modal dialog asking for RDP credentials when not stored in vault."""

    def __init__(
        self,
        hostname: str = "",
        username: str = "",
        domain: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("RDP Credentials")
        self.setFixedSize(400, 300)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(12)

        title = QLabel(f"Connect to {hostname}")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {Colors.TEXT_PRIMARY};"
        )
        layout.addWidget(title)

        subtitle = QLabel("Enter your Windows credentials:")
        subtitle.setStyleSheet(f"font-size: 12px; color: {Colors.TEXT_MUTED};")
        layout.addWidget(subtitle)

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

        layout.addStretch()

        # Connect button
        connect_btn = QPushButton("Connect")
        connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        connect_btn.setStyleSheet(
            f"QPushButton {{ background-color: {Colors.ACCENT}; color: #fff; "
            f"border: none; border-radius: 6px; padding: 8px 16px; font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: {Colors.ACCENT_HOVER}; }}"
        )
        connect_btn.clicked.connect(self.accept)
        layout.addWidget(connect_btn)

        self._password_edit.returnPressed.connect(self.accept)

        self.setStyleSheet(
            f"QDialog {{ background-color: {Colors.BG_PRIMARY}; }}"
            f"QLineEdit {{ background-color: {Colors.BG_TERTIARY}; color: {Colors.TEXT_PRIMARY}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 4px; padding: 6px 10px; }}"
        )

        # Focus first empty field
        if username:
            self._password_edit.setFocus()
        else:
            self._username_edit.setFocus()

    def username(self) -> str:
        return self._username_edit.text()

    def password(self) -> str:
        return self._password_edit.text()

    def domain(self) -> str:
        return self._domain_edit.text()
