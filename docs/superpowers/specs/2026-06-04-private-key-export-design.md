# Design: Export Private Key from Vault

**Date:** 2026-06-04  
**Feature:** Download/export SSH private key from Keychain view in the Vault, gated behind master password re-authentication.

---

## Overview

Users can already export the public key from the SSH Keys section of the Vault. This feature adds the ability to export the **private key** to a file. Because private keys are sensitive, the user must re-enter the master password every time — even if the vault is already unlocked — to prevent unauthorized export by someone with physical access to an unlocked session.

---

## Architecture

### New file: `rlqshell/ui/vault/private_key_export_dialog.py`

A modal `QDialog` with a `QStackedWidget` (two phases), following the same pattern as `PasswordViewDialog`.

**Phase 1 — Master password confirmation**

- Context header widget: key label, type badge, fingerprint (same visual style as `PasswordViewDialog._context_header`)
- Description label: "Podaj hasło główne, aby wyeksportować klucz prywatny."
- `QLineEdit` (password echo mode) for the master password
- "Potwierdź" button → calls `credential_store.unlock(entered)`; on failure shows error, clears field
- "Anuluj" button → rejects dialog

**Phase 2 — Export**

- Same context header
- Status `QLabel` (initially empty, shows success or error after save attempt)
- "Zapisz do pliku" `QPushButton` → opens `QFileDialog.getSaveFileName` with default filename `id_<key_type>` (e.g. `id_ed25519`), filter `"All Files (*)"`, writes decrypted PEM bytes
- "Zamknij" `QPushButton` → accepts dialog

**Constructor signature:**
```python
PrivateKeyExportDialog(
    credential_store: CredentialStore,
    keychain: Keychain,
    key: SSHKey,
    parent: QWidget | None = None,
)
```

**Security cleanup in `done()`:**
- Sets internal `_pem: bytes | None = None` before calling `super().done()`
- Clears the master password `QLineEdit` after successful unlock

---

### Modified: `rlqshell/ui/vault/keychain_view.py`

**Constructor change:**
```python
def __init__(
    self,
    keychain: Keychain,
    credential_store: CredentialStore | None = None,
    vault_locked: bool = False,
    parent: QWidget | None = None,
) -> None:
```
`credential_store` stored as `self._credential_store`.

**Context menu change in `_show_context_menu`:**

Add "Export Private Key" action between "Export Public Key" and the separator before "Delete". Only added when `self._credential_store is not None`.

```
Copy Public Key
Export Public Key
Export Private Key    ← new (only if credential_store available)
────────────────────
Delete
```

**New method:**
```python
def _export_private_key(self, key_id: int) -> None:
    key = next((k for k in self._keychain.list_keys() if k.id == key_id), None)
    if key is None:
        return
    from rlqshell.ui.vault.private_key_export_dialog import PrivateKeyExportDialog
    dlg = PrivateKeyExportDialog(self._credential_store, self._keychain, key, parent=self)
    dlg.exec()
```

---

### Modified: `rlqshell/ui/vault/vault_page.py`

Pass `credential_store` when constructing `KeychainView`:

```python
self._keychain_section = KeychainView(
    keychain,
    credential_store=credential_store,
    vault_locked=self._vault_locked,
)
```

---

## Error Handling

| Scenario | Behavior |
|---|---|
| `credential_store` is `None` | "Export Private Key" not shown in context menu |
| Wrong master password | Error label in Phase 1, field cleared, focus returned |
| `export_private_key()` returns `None` | Error shown in Phase 2, save button disabled |
| File write fails (permission, disk full) | `QMessageBox.warning` with exception message |

---

## File naming defaults

| Key type | Default filename |
|---|---|
| ed25519 | `id_ed25519` |
| rsa | `id_rsa` |
| ecdsa | `id_ecdsa` |
| other | `id_key` |

---

## Out of scope

- Re-encrypting the exported key with a new passphrase (export always writes what's stored)
- Showing the raw PEM content inline (no clipboard copy for private keys)
