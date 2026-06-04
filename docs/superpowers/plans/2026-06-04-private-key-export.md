# Private Key Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add "Export Private Key" to the SSH Keys context menu in the Vault, gated behind master password re-authentication, saving the decrypted PEM to a user-selected file.

**Architecture:** New `PrivateKeyExportDialog` (two-phase QStackedWidget: master password → file save) follows the same pattern as the existing `PasswordViewDialog`. `KeychainView` gains an optional `credential_store` parameter and adds the menu entry. `VaultPage` passes `credential_store` to `KeychainView`.

**Tech Stack:** PySide6 (Qt 6), `rlqshell.core.credential_store.CredentialStore`, `rlqshell.core.keychain.Keychain`, `rlqshell.core.models.ssh_key.SSHKey`, pytest + pytest-qt.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `rlqshell/ui/vault/private_key_export_dialog.py` | Two-phase modal dialog: password confirm → file save |
| Create | `tests/test_private_key_export.py` | Tests for the dialog and KeychainView changes |
| Modify | `rlqshell/ui/vault/keychain_view.py` | Add `credential_store` param, context menu entry, `_export_private_key` |
| Modify | `rlqshell/ui/vault/vault_page.py` | Pass `credential_store` when constructing `KeychainView` |

---

## Task 1: Tests for `PrivateKeyExportDialog`

**Files:**
- Create: `tests/test_private_key_export.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for PrivateKeyExportDialog and KeychainView private key export."""

from __future__ import annotations

from pathlib import Path

import pytest

from rlqshell.core.credential_store import CredentialStore
from rlqshell.core.database import Database
from rlqshell.core.keychain import Keychain


@pytest.fixture
def vault(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    store = CredentialStore(db, tmp_path / "vault.key")
    store.set_master_password("correct-password")
    keychain = Keychain(db, store)
    key = keychain.generate_key(key_type="ed25519", label="test-key")
    yield store, keychain, key
    db.close()


def test_dialog_starts_at_phase1(qtbot, vault):
    from rlqshell.ui.vault.private_key_export_dialog import PrivateKeyExportDialog

    store, keychain, key = vault
    dlg = PrivateKeyExportDialog(store, keychain, key)
    qtbot.addWidget(dlg)

    assert dlg._stack.currentIndex() == 0


def test_wrong_password_stays_in_phase1(qtbot, vault):
    from rlqshell.ui.vault.private_key_export_dialog import PrivateKeyExportDialog

    store, keychain, key = vault
    dlg = PrivateKeyExportDialog(store, keychain, key)
    qtbot.addWidget(dlg)

    dlg._master_pwd_edit.setText("wrong-password")
    dlg._confirm()

    assert dlg._stack.currentIndex() == 0
    assert dlg._error_label.isVisible()


def test_correct_password_advances_to_phase2(qtbot, vault):
    from rlqshell.ui.vault.private_key_export_dialog import PrivateKeyExportDialog

    store, keychain, key = vault
    dlg = PrivateKeyExportDialog(store, keychain, key)
    qtbot.addWidget(dlg)

    dlg._master_pwd_edit.setText("correct-password")
    dlg._confirm()

    assert dlg._stack.currentIndex() == 1
    assert dlg._pem is not None


def test_done_clears_pem(qtbot, vault):
    from rlqshell.ui.vault.private_key_export_dialog import PrivateKeyExportDialog

    store, keychain, key = vault
    dlg = PrivateKeyExportDialog(store, keychain, key)
    qtbot.addWidget(dlg)

    dlg._master_pwd_edit.setText("correct-password")
    dlg._confirm()
    assert dlg._pem is not None

    dlg.done(0)
    assert dlg._pem is None


def test_empty_password_shows_error(qtbot, vault):
    from rlqshell.ui.vault.private_key_export_dialog import PrivateKeyExportDialog

    store, keychain, key = vault
    dlg = PrivateKeyExportDialog(store, keychain, key)
    qtbot.addWidget(dlg)

    dlg._master_pwd_edit.setText("")
    dlg._confirm()

    assert dlg._stack.currentIndex() == 0
    assert dlg._error_label.isVisible()


def test_save_to_file_writes_pem(qtbot, vault, tmp_path, monkeypatch):
    from rlqshell.ui.vault.private_key_export_dialog import PrivateKeyExportDialog
    from PySide6.QtWidgets import QFileDialog

    store, keychain, key = vault
    out_path = str(tmp_path / "id_ed25519")
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *a, **kw: (out_path, ""),
    )

    dlg = PrivateKeyExportDialog(store, keychain, key)
    qtbot.addWidget(dlg)

    dlg._master_pwd_edit.setText("correct-password")
    dlg._confirm()
    dlg._save_to_file()

    saved = Path(out_path).read_bytes()
    assert saved.startswith(b"-----BEGIN")


def test_keychain_view_stores_credential_store(qtbot, vault):
    from rlqshell.ui.vault.keychain_view import KeychainView

    store, keychain, _ = vault
    view = KeychainView(keychain, credential_store=store)
    qtbot.addWidget(view)

    assert view._credential_store is store


def test_keychain_view_none_credential_store(qtbot, vault):
    from rlqshell.ui.vault.keychain_view import KeychainView

    _, keychain, _ = vault
    view = KeychainView(keychain, credential_store=None)
    qtbot.addWidget(view)

    assert view._credential_store is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_private_key_export.py -v
```

Expected: `ImportError` or `AttributeError` — `PrivateKeyExportDialog` does not exist yet.

---

## Task 2: Create `PrivateKeyExportDialog`

**Files:**
- Create: `rlqshell/ui/vault/private_key_export_dialog.py`

- [ ] **Step 3: Create the dialog**

```python
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
```

- [ ] **Step 4: Run tests — first 6 should pass, last 2 still fail**

```
pytest tests/test_private_key_export.py -v
```

Expected:
- `test_dialog_starts_at_phase1` → PASS
- `test_wrong_password_stays_in_phase1` → PASS
- `test_correct_password_advances_to_phase2` → PASS
- `test_done_clears_pem` → PASS
- `test_empty_password_shows_error` → PASS
- `test_save_to_file_writes_pem` → PASS
- `test_keychain_view_stores_credential_store` → FAIL (AttributeError: `_credential_store`)
- `test_keychain_view_none_credential_store` → FAIL (AttributeError: `_credential_store`)

- [ ] **Step 5: Commit**

```
git add rlqshell/ui/vault/private_key_export_dialog.py tests/test_private_key_export.py
git commit -m "feat: add PrivateKeyExportDialog with master password gate"
```

---

## Task 3: Update `KeychainView`

**Files:**
- Modify: `rlqshell/ui/vault/keychain_view.py`

Current `KeychainView.__init__` signature (line 197):
```python
def __init__(self, keychain: Keychain, vault_locked: bool = False, parent: QWidget | None = None) -> None:
```

- [ ] **Step 6: Add `credential_store` parameter and store it**

In `rlqshell/ui/vault/keychain_view.py`, change the `__init__` signature and add storage:

Old:
```python
    def __init__(self, keychain: Keychain, vault_locked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._keychain = keychain
        self._vault_locked = vault_locked
```

New:
```python
    def __init__(
        self,
        keychain: Keychain,
        credential_store: CredentialStore | None = None,
        vault_locked: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._keychain = keychain
        self._credential_store = credential_store
        self._vault_locked = vault_locked
```

Also add the import at the top of the file (after existing imports):
```python
from rlqshell.core.credential_store import CredentialStore
```

- [ ] **Step 7: Add "Export Private Key" to context menu in `_show_context_menu`**

Old `_show_context_menu` (line 334):
```python
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
```

New:
```python
    def _show_context_menu(self, key_id: int, pos) -> None:
        if self._vault_locked:
            return
        menu = QMenu(self)

        copy_pub = menu.addAction("Copy Public Key")
        copy_pub.triggered.connect(lambda: self._copy_public_key(key_id))

        export_pub = menu.addAction("Export Public Key")
        export_pub.triggered.connect(lambda: self._export_public_key(key_id))

        if self._credential_store is not None:
            export_priv = menu.addAction("Export Private Key")
            export_priv.triggered.connect(lambda: self._export_private_key(key_id))

        menu.addSeparator()

        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self._delete_key(key_id))

        menu.exec(pos)
```

- [ ] **Step 8: Add `_export_private_key` method**

Add after `_export_public_key` (after line 374):
```python
    def _export_private_key(self, key_id: int) -> None:
        key = next((k for k in self._keychain.list_keys() if k.id == key_id), None)
        if key is None:
            return
        from rlqshell.ui.vault.private_key_export_dialog import PrivateKeyExportDialog

        dlg = PrivateKeyExportDialog(self._credential_store, self._keychain, key, parent=self)
        dlg.exec()
```

- [ ] **Step 9: Run all KeychainView tests**

```
pytest tests/test_private_key_export.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 10: Commit**

```
git add rlqshell/ui/vault/keychain_view.py
git commit -m "feat: add Export Private Key to KeychainView context menu"
```

---

## Task 4: Update `VaultPage`

**Files:**
- Modify: `rlqshell/ui/vault/vault_page.py`

Current `KeychainView` construction (line 122):
```python
        if keychain is not None:
            self._keychain_section: QWidget = KeychainView(
                keychain, vault_locked=self._vault_locked
            )
```

- [ ] **Step 11: Pass `credential_store` to `KeychainView`**

Old:
```python
            self._keychain_section: QWidget = KeychainView(
                keychain, vault_locked=self._vault_locked
            )
```

New:
```python
            self._keychain_section: QWidget = KeychainView(
                keychain,
                credential_store=credential_store,
                vault_locked=self._vault_locked,
            )
```

- [ ] **Step 12: Run full test suite**

```
pytest -v
```

Expected: all tests PASS, no regressions.

- [ ] **Step 13: Commit**

```
git add rlqshell/ui/vault/vault_page.py
git commit -m "feat: wire credential_store into KeychainView from VaultPage"
```

---

## Self-Review

**Spec coverage:**
- ✅ "Export Private Key" in context menu → Task 3, Step 7
- ✅ Master password re-auth always required → `_confirm()` calls `unlock()` unconditionally
- ✅ Phase 1: wrong password shows error, stays in phase 1 → tested in Task 1
- ✅ Phase 2: file save with default name per key type → `_DEFAULT_NAMES` + `_save_to_file()`
- ✅ PEM cleared in `done()` → tested in Task 1
- ✅ No "Export Private Key" when `credential_store` is None → Task 3, Step 7 condition
- ✅ File write error shown via `QMessageBox.warning` → `_save_to_file()` except block
- ✅ `VaultPage` passes `credential_store` → Task 4

**Placeholder scan:** None found.

**Type consistency:**
- `PrivateKeyExportDialog(credential_store, keychain, key, parent)` — used identically in Task 2 (creation) and Task 3 (`_export_private_key` call).
- `_credential_store` attribute — set in Task 3 Step 6, read in Task 3 Steps 7 and 8.
- `_pem: bytes | None` — set in `_confirm()`, read in `_save_to_file()`, cleared in `done()`.
