"""Password view dialog — reveal a saved credential after master password re-auth."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import ICONS_DIR, Colors
from rlqshell.core.credential_store import CredentialStore
from rlqshell.core.models.credential import Identity


class PasswordViewDialog(QDialog):
    """Two-phase dialog: confirm master password, then reveal the stored credential.

    Phase 1 — re-authentication: user enters master password.
    Phase 2 — password reveal: masked field, eye toggle, copy button.
    """

    def __init__(
        self,
        credential_store: CredentialStore,
        identity: Identity,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = credential_store
        self._identity = identity
        self._plaintext: str | None = None

        self.setWindowTitle("View Password")
        self.setFixedSize(420, 300)
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

        desc = QLabel("Podaj hasło główne, aby wyświetlić zapisane hasło.")
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
    # Phase 2 — password reveal
    # ------------------------------------------------------------------

    def _build_phase2(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        layout.addWidget(self._context_header())

        layout.addWidget(self._field_label("Hasło"))

        pwd_row = QHBoxLayout()
        pwd_row.setSpacing(6)

        self._pwd_display = QLineEdit()
        self._pwd_display.setEchoMode(QLineEdit.EchoMode.Password)
        self._pwd_display.setReadOnly(True)
        pwd_row.addWidget(self._pwd_display, 1)

        self._eye_btn = QPushButton()
        self._eye_btn.setObjectName("iconBtn")
        self._eye_btn.setFixedSize(36, 36)
        self._eye_btn.setToolTip("Pokaż / ukryj hasło")
        self._eye_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._eye_btn.setCheckable(True)
        self._eye_btn.setIconSize(QSize(18, 18))
        self._icon_eye_open = QIcon(str(ICONS_DIR / "eye_open.svg"))
        self._icon_eye_closed = QIcon(str(ICONS_DIR / "eye_closed.svg"))
        self._eye_btn.setIcon(self._icon_eye_closed)
        self._eye_btn.toggled.connect(self._toggle_visibility)
        pwd_row.addWidget(self._eye_btn)

        self._copy_btn = QPushButton("Kopiuj")
        self._copy_btn.setObjectName("copyBtn")
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.clicked.connect(self._copy_password)
        pwd_row.addWidget(self._copy_btn)

        layout.addLayout(pwd_row)
        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Zamknij")
        close_btn.setObjectName("primaryBtn")
        close_btn.setDefault(True)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
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

        lbl = QLabel(self._identity.label or "Unnamed")
        lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {Colors.TEXT_PRIMARY};"
            f" background: transparent;"
        )
        layout.addWidget(lbl)

        user = QLabel(self._identity.username)
        user.setStyleSheet(
            f"font-size: 11px; color: {Colors.TEXT_MUTED}; background: transparent;"
            f" font-family: 'JetBrains Mono', monospace;"
        )
        layout.addWidget(user)

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

        self._plaintext = self._store.get_decrypted_password(self._identity.id)  # type: ignore[arg-type]
        if self._plaintext is None:
            self._show_error("Nie można odczytać hasła — brak danych.")
            return

        self._master_pwd_edit.clear()
        self._pwd_display.setText(self._plaintext)
        self._stack.setCurrentIndex(1)

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._error_label.setVisible(True)

    def _toggle_visibility(self, checked: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self._pwd_display.setEchoMode(mode)
        self._eye_btn.setIcon(self._icon_eye_open if checked else self._icon_eye_closed)

    def _copy_password(self) -> None:
        if self._plaintext:
            QGuiApplication.clipboard().setText(self._plaintext)
            self._copy_btn.setText("Skopiowano!")
            QTimer.singleShot(2000, lambda: self._copy_btn.setText("Kopiuj"))

    def done(self, result: int) -> None:
        self._plaintext = None
        self._pwd_display.clear()
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
            QPushButton#copyBtn {{
                background-color: transparent;
                color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 8px 14px;
                font-size: 12px;
            }}
            QPushButton#copyBtn:hover {{
                background-color: {Colors.BG_HOVER};
                color: {Colors.TEXT_PRIMARY};
            }}
            QPushButton#iconBtn {{
                background-color: transparent;
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                font-size: 16px;
            }}
            QPushButton#iconBtn:hover {{
                background-color: {Colors.BG_HOVER};
            }}
            QPushButton#iconBtn:checked {{
                background-color: {Colors.BG_HOVER};
                border-color: {Colors.ACCENT};
            }}
        """)
