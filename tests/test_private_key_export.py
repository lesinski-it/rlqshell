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
    assert not dlg._error_label.isHidden()


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
    assert not dlg._error_label.isHidden()


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
