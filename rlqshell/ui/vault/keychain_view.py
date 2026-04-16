"""Keychain view — SSH key management UI."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import Colors
from rlqshell.core.keychain import Keychain
from rlqshell.core.models.ssh_key import SSHKey
from rlqshell.ui.widgets.empty_state import EmptyState

logger = logging.getLogger(__name__)


class _KeyListItem(QWidget):
    """Single SSH key row."""

    clicked = Signal(int)  # key_id
    context_menu_requested = Signal(int, object)  # key_id, QPoint

    def __init__(self, key: SSHKey, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._key_id = key.id or 0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(68)
        self.setStyleSheet(
            f"_KeyListItem {{ background: transparent; border-radius: 6px; }}"
            f"_KeyListItem:hover {{ background-color: {Colors.BG_SURFACE}; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        # Key type badge
        type_label = QLabel(key.key_type.upper())
        type_label.setFixedWidth(60)
        type_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        type_label.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {Colors.ACCENT_LIGHT}; "
            f"background-color: {Colors.BG_HOVER}; border-radius: 4px; "
            f"padding: 4px 6px;"
        )
        layout.addWidget(type_label)

        # Label + fingerprint
        info_layout = QVBoxLayout()
        info_layout.setSpacing(5)
        info_layout.setContentsMargins(0, 0, 0, 0)

        label_text = key.label or "Unnamed key"
        name_label = QLabel(label_text)
        name_label.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        info_layout.addWidget(name_label)

        fp_text = key.fingerprint or ""
        if len(fp_text) > 50:
            fp_text = fp_text[:50] + "..."
        fp_label = QLabel(fp_text)
        fp_label.setStyleSheet(
            f"font-size: 11px; color: {Colors.TEXT_MUTED}; background: transparent; "
            f"font-family: 'JetBrains Mono', monospace;"
        )
        info_layout.addWidget(fp_label)

        layout.addLayout(info_layout, 1)

        # Bits
        bits_label = QLabel(f"{key.bits} bit" if key.bits else "")
        bits_label.setStyleSheet(
            f"font-size: 11px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        layout.addWidget(bits_label)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._key_id)
        elif event.button() == Qt.MouseButton.RightButton:
            self.context_menu_requested.emit(self._key_id, event.globalPosition().toPoint())
        super().mousePressEvent(event)


class GenerateKeyDialog(QDialog):
    """Dialog for generating a new SSH key."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Generate SSH Key")
        self.setFixedSize(420, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # Label
        layout.addWidget(self._make_label("Label"))
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("e.g. my-server-key")
        layout.addWidget(self.label_edit)

        # Key type
        layout.addWidget(self._make_label("Key Type"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["ed25519", "rsa", "ecdsa"])
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        layout.addWidget(self.type_combo)

        # Bits (only for RSA/ECDSA)
        layout.addWidget(self._make_label("Key Size (bits)"))
        self.bits_spin = QSpinBox()
        self.bits_spin.setRange(256, 8192)
        self.bits_spin.setValue(4096)
        self.bits_spin.setSingleStep(1024)
        self.bits_spin.setEnabled(False)  # Ed25519 is fixed
        layout.addWidget(self.bits_spin)

        # Passphrase
        layout.addWidget(self._make_label("Passphrase (optional)"))
        self.passphrase_edit = QLineEdit()
        self.passphrase_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.passphrase_edit.setPlaceholderText("Leave empty for no passphrase")
        layout.addWidget(self.passphrase_edit)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        generate_btn = QPushButton("Generate")
        generate_btn.setProperty("cssClass", "primary")
        generate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        generate_btn.clicked.connect(self.accept)
        btn_layout.addWidget(generate_btn)

        layout.addLayout(btn_layout)

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_SECONDARY}; "
            f"background: transparent;"
        )
        return lbl

    def _on_type_changed(self, key_type: str) -> None:
        if key_type == "ed25519":
            self.bits_spin.setEnabled(False)
            self.bits_spin.setValue(256)
        elif key_type == "rsa":
            self.bits_spin.setEnabled(True)
            self.bits_spin.setValue(4096)
            self.bits_spin.setRange(2048, 8192)
            self.bits_spin.setSingleStep(1024)
        elif key_type == "ecdsa":
            self.bits_spin.setEnabled(True)
            self.bits_spin.setValue(256)
            self.bits_spin.setRange(256, 384)
            self.bits_spin.setSingleStep(128)

    def get_params(self) -> dict:
        return {
            "label": self.label_edit.text().strip(),
            "key_type": self.type_combo.currentText(),
            "bits": self.bits_spin.value(),
            "passphrase": self.passphrase_edit.text() or None,
        }


class KeychainView(QWidget):
    """SSH key management view — list, generate, import, export, delete."""

    def __init__(self, keychain: Keychain, vault_locked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._keychain = keychain
        self._vault_locked = vault_locked

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setFixedHeight(52)
        toolbar.setStyleSheet(
            f"background-color: {Colors.BG_PRIMARY}; "
            f"border-bottom: 1px solid {Colors.BORDER};"
        )
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 8, 16, 8)
        toolbar_layout.setSpacing(8)

        title = QLabel("SSH Keys")
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        toolbar_layout.addWidget(title)
        toolbar_layout.addStretch()

        import_btn = QPushButton("Import")
        import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        import_btn.clicked.connect(self._on_import_key)
        if vault_locked:
            import_btn.setEnabled(False)
            import_btn.setToolTip("Vault is locked \u2014 enter master password at startup")
        toolbar_layout.addWidget(import_btn)

        generate_btn = QPushButton("Generate Key")
        generate_btn.setProperty("cssClass", "primary")
        generate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        generate_btn.clicked.connect(self._on_generate_key)
        if vault_locked:
            generate_btn.setEnabled(False)
            generate_btn.setToolTip("Vault is locked \u2014 enter master password at startup")
        toolbar_layout.addWidget(generate_btn)

        layout.addWidget(toolbar)

        # Scroll area for key list
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        layout.addWidget(self._scroll)

        # Container for keys
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(8, 8, 8, 8)
        self._list_layout.setSpacing(2)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._list_container)

        # Empty state
        self._empty_state = EmptyState(
            title="No SSH Keys",
            description="Generate or import SSH keys to authenticate with servers.",
            action_text="Generate Key",
            icon_text="🔑",
        )
        self._empty_state.action_clicked.connect(self._on_generate_key)

        self.refresh()

    def refresh(self) -> None:
        """Reload the key list from the database."""
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

        keys = self._keychain.list_keys()

        if not keys:
            self._list_layout.addWidget(self._empty_state)
            self._empty_state.show()
            return

        self._empty_state.hide()

        for key in keys:
            item = _KeyListItem(key)
            item.context_menu_requested.connect(self._show_context_menu)
            self._list_layout.addWidget(item)

    def _on_generate_key(self) -> None:
        dialog = GenerateKeyDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            params = dialog.get_params()
            try:
                self._keychain.generate_key(
                    key_type=params["key_type"],
                    bits=params["bits"],
                    passphrase=params["passphrase"],
                    label=params["label"],
                )
                logger.info("Generated %s key: %s", params["key_type"], params["label"])
                self.refresh()
            except Exception:
                logger.exception("Failed to generate key")

    def _on_import_key(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import SSH Private Key", "",
            "All Files (*);;PEM Files (*.pem);;Key Files (*.key *.id_rsa *.id_ed25519)",
        )
        if not file_path:
            return

        try:
            with open(file_path, "rb") as f:
                pem_data = f.read()
            self._keychain.import_key(pem_data, label=file_path.split("/")[-1])
            logger.info("Imported key from %s", file_path)
            self.refresh()
        except Exception:
            logger.exception("Failed to import key from %s", file_path)

    def _show_context_menu(self, key_id: int, pos) -> None:
        if self._vault_locked:
            return
        menu = QMenu(self)

        copy_pub = menu.addAction("Copy Public Key")
        copy_pub.triggered.connect(lambda: self._copy_public_key(key_id))

        export_pub = menu.addAction("Export Public Key")
        export_pub.triggered.connect(lambda: self._export_public_key(key_id))

        menu.addSeparator()

        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self._delete_key(key_id))

        menu.exec(pos)

    def _copy_public_key(self, key_id: int) -> None:
        pub = self._keychain.export_public_key(key_id)
        if pub:
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(pub)
            logger.info("Public key copied to clipboard")

    def _export_public_key(self, key_id: int) -> None:
        from PySide6.QtWidgets import QFileDialog

        pub = self._keychain.export_public_key(key_id)
        if not pub:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Public Key", "id_key.pub",
            "Public Key Files (*.pub);;All Files (*)",
        )
        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(pub)
            logger.info("Public key exported to %s", file_path)

    def _delete_key(self, key_id: int) -> None:
        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self, "Delete Key",
            "Are you sure you want to delete this SSH key?\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._keychain.delete_key(key_id)
            logger.info("Deleted key %d", key_id)
            self.refresh()
