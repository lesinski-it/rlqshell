"""Identities view — manage saved credentials (create, edit, delete)."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import Colors
from rlqshell.core.credential_store import CredentialStore
from rlqshell.core.keychain import Keychain
from rlqshell.core.models.credential import Identity
from rlqshell.ui.widgets.empty_state import EmptyState

logger = logging.getLogger(__name__)


class _IdentityListItem(QWidget):
    """Single identity row."""

    clicked = Signal(int)  # identity_id
    context_menu_requested = Signal(int, object)  # identity_id, QPoint

    def __init__(self, identity: Identity, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._identity_id = identity.id or 0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(68)
        self.setStyleSheet(
            f"_IdentityListItem {{ background: transparent; border-radius: 6px; }}"
            f"_IdentityListItem:hover {{ background-color: {Colors.BG_SURFACE}; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        # Auth type badge
        auth_label = QLabel(identity.auth_type.upper())
        auth_label.setFixedWidth(80)
        auth_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        auth_label.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {Colors.ACCENT_LIGHT}; "
            f"background-color: {Colors.BG_HOVER}; border-radius: 4px; "
            f"padding: 4px 6px;"
        )
        layout.addWidget(auth_label)

        # Label + username
        info_layout = QVBoxLayout()
        info_layout.setSpacing(5)
        info_layout.setContentsMargins(0, 0, 0, 0)

        label_text = identity.label or "Unnamed"
        name_label = QLabel(label_text)
        name_label.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        info_layout.addWidget(name_label)

        username_label = QLabel(identity.username)
        username_label.setStyleSheet(
            f"font-size: 11px; color: {Colors.TEXT_MUTED}; background: transparent; "
            f"font-family: 'JetBrains Mono', monospace;"
        )
        info_layout.addWidget(username_label)

        layout.addLayout(info_layout, 1)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._identity_id)
        elif event.button() == Qt.MouseButton.RightButton:
            self.context_menu_requested.emit(
                self._identity_id, event.globalPosition().toPoint()
            )
        super().mousePressEvent(event)


class IdentitiesView(QWidget):
    """Identity management view — list, create, edit, delete credentials."""

    def __init__(
        self,
        credential_store: CredentialStore,
        keychain: Keychain,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = credential_store
        self._keychain = keychain

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setFixedHeight(52)
        toolbar.setStyleSheet(
            f"background-color: {Colors.BG_PRIMARY}; "
            f"border-bottom: 1px solid {Colors.BORDER};"
            f" QPushButton#changePwdBtn {{"
            f" background-color: transparent; color: {Colors.TEXT_MUTED};"
            f" border: 1px solid {Colors.BORDER}; border-radius: 6px;"
            f" padding: 6px 14px; font-size: 12px; }}"
            f" QPushButton#changePwdBtn:hover {{"
            f" background-color: {Colors.BG_HOVER}; color: {Colors.TEXT_PRIMARY}; }}"
        )
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 8, 16, 8)
        toolbar_layout.setSpacing(8)

        title = QLabel("Identities")
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        toolbar_layout.addWidget(title)
        toolbar_layout.addStretch()

        add_btn = QPushButton("New Identity")
        add_btn.setProperty("cssClass", "primary")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_new_identity)
        if not credential_store.is_unlocked:
            add_btn.setEnabled(False)
            add_btn.setToolTip("Vault is locked \u2014 enter master password at startup")
        toolbar_layout.addWidget(add_btn)

        if credential_store.is_unlocked:
            change_pwd_btn = QPushButton("Change Password")
            change_pwd_btn.setObjectName("changePwdBtn")
            change_pwd_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            change_pwd_btn.clicked.connect(self._on_change_master_password)
            toolbar_layout.addWidget(change_pwd_btn)

        layout.addWidget(toolbar)

        # Scroll area for identity list
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )
        layout.addWidget(self._scroll)

        # Container for identities
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(8, 8, 8, 8)
        self._list_layout.setSpacing(2)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._list_container)

        # Empty state
        self._empty_state = EmptyState(
            title="No Identities",
            description="Create identities to store usernames and credentials for your hosts.",
            action_text="New Identity",
            icon_text="\U0001f464",  # 👤
        )
        self._empty_state.action_clicked.connect(self._on_new_identity)

        self.refresh()

    def refresh(self) -> None:
        """Reload the identity list from the database."""
        # Clear existing items, but keep the persistent empty-state widget alive
        # (deleteLater on it would dangle the C++ object on the next refresh).
        for i in reversed(range(self._list_layout.count())):
            widget = self._list_layout.itemAt(i).widget()
            if widget is None:
                continue
            if widget is self._empty_state:
                self._list_layout.takeAt(i)
                widget.setParent(None)
            else:
                self._list_layout.takeAt(i)
                widget.deleteLater()

        identities = self._store.list_identities()

        if not identities:
            self._list_layout.addWidget(self._empty_state)
            self._empty_state.show()
            return

        self._empty_state.hide()

        for identity in identities:
            item = _IdentityListItem(identity)
            item.clicked.connect(self._on_edit_identity)
            item.context_menu_requested.connect(self._show_context_menu)
            self._list_layout.addWidget(item)

    def _on_change_master_password(self) -> None:
        from rlqshell.ui.dialogs.change_master_password_dialog import (
            ChangeMasterPasswordDialog,
        )

        dlg = ChangeMasterPasswordDialog(self._store, parent=self)
        dlg.exec()

    def _require_unlocked(self) -> bool:
        """Return True if the vault is unlocked; show a warning otherwise."""
        if self._store.is_unlocked:
            return True
        QMessageBox.warning(
            self,
            "Vault Locked",
            "The vault is locked. Enter the master password at startup\n"
            "to create or edit identities.",
        )
        return False

    def _on_new_identity(self) -> None:
        if not self._require_unlocked():
            return
        from rlqshell.ui.vault.identity_editor import IdentityEditor

        dialog = IdentityEditor(self._store, self._keychain, parent=self)
        dialog.identity_saved.connect(lambda _: self.refresh())
        dialog.exec()

    def _on_edit_identity(self, identity_id: int) -> None:
        if not self._require_unlocked():
            return
        from rlqshell.ui.vault.identity_editor import IdentityEditor

        dialog = IdentityEditor(
            self._store, self._keychain, parent=self, identity_id=identity_id
        )
        dialog.identity_saved.connect(lambda _: self.refresh())
        dialog.exec()

    def _show_context_menu(self, identity_id: int, pos) -> None:
        menu = QMenu(self)

        edit_action = menu.addAction("Edit")
        edit_action.triggered.connect(lambda: self._on_edit_identity(identity_id))

        menu.addSeparator()

        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self._delete_identity(identity_id))

        menu.exec(pos)

    def _delete_identity(self, identity_id: int) -> None:
        if not self._require_unlocked():
            return
        identity = self._store.get_identity(identity_id)
        label = identity.label if identity else "this identity"

        reply = QMessageBox.question(
            self,
            "Delete Identity",
            f"Are you sure you want to delete \"{label}\"?\n"
            "Hosts using this identity will need a new one assigned.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._store.delete_identity(identity_id)
            logger.info("Deleted identity %d", identity_id)
            self.refresh()
