"""Tests for CredentialStore and Keychain."""

from __future__ import annotations

from pathlib import Path

import pytest

from termplus.core.credential_store import CredentialStore
from termplus.core.database import Database
from termplus.core.keychain import Keychain
from termplus.utils.crypto import decrypt, derive_key, encrypt, generate_salt


# === Crypto utils ===

def test_encrypt_decrypt_roundtrip():
    salt = generate_salt()
    key = derive_key("test-password", salt)
    plaintext = b"Hello, Termplus!"
    ciphertext = encrypt(plaintext, key)
    assert ciphertext != plaintext
    assert decrypt(ciphertext, key) == plaintext


def test_derive_key_deterministic():
    salt = generate_salt()
    k1 = derive_key("password", salt)
    k2 = derive_key("password", salt)
    assert k1 == k2


def test_wrong_password_fails():
    from cryptography.fernet import InvalidToken

    salt = generate_salt()
    key1 = derive_key("right", salt)
    key2 = derive_key("wrong", salt)
    ct = encrypt(b"secret", key1)
    with pytest.raises(InvalidToken):
        decrypt(ct, key2)


# === CredentialStore ===

def test_set_and_unlock_master_password(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    store = CredentialStore(db, tmp_path / "vault.key")

    assert not store.has_master_password
    store.set_master_password("my-secret")
    assert store.has_master_password
    assert store.is_unlocked

    store.lock()
    assert not store.is_unlocked

    assert store.unlock("my-secret")
    assert store.is_unlocked
    db.close()


def test_wrong_master_password(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    store = CredentialStore(db, tmp_path / "vault.key")

    store.set_master_password("correct")
    store.lock()
    assert not store.unlock("wrong")
    assert not store.is_unlocked
    db.close()


def test_encrypt_decrypt_password(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    store = CredentialStore(db, tmp_path / "vault.key")
    store.set_master_password("master")

    ct = store.encrypt_password("ssh-password-123")
    assert ct != b"ssh-password-123"
    assert store.decrypt_password(ct) == "ssh-password-123"
    db.close()


def test_identity_crud(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    store = CredentialStore(db, tmp_path / "vault.key")
    store.set_master_password("master")

    identity_id = store.create_identity(
        label="admin@prod", username="admin",
        auth_type="password", password="secret123",
    )
    assert identity_id > 0

    identity = store.get_identity(identity_id)
    assert identity is not None
    assert identity.label == "admin@prod"
    assert identity.username == "admin"
    assert identity.encrypted_password is not None

    decrypted = store.get_decrypted_password(identity_id)
    assert decrypted == "secret123"

    identities = store.list_identities()
    assert len(identities) == 1

    store.delete_identity(identity_id)
    assert store.get_identity(identity_id) is None
    db.close()


# === Keychain ===

def test_generate_ed25519_key(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    store = CredentialStore(db, tmp_path / "vault.key")
    store.set_master_password("master")
    keychain = Keychain(db, store)

    key = keychain.generate_key(
        key_type="ed25519", label="test-key",
    )
    assert key.id is not None
    assert key.key_type == "ed25519"
    assert key.fingerprint.startswith("SHA256:")
    assert key.public_key.startswith("ssh-ed25519")
    assert key.bits == 256
    db.close()


def test_generate_rsa_key(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    store = CredentialStore(db, tmp_path / "vault.key")
    store.set_master_password("master")
    keychain = Keychain(db, store)

    key = keychain.generate_key(
        key_type="rsa", bits=2048, label="rsa-test",
    )
    assert key.key_type == "rsa"
    assert key.bits == 2048
    assert key.public_key.startswith("ssh-rsa")
    db.close()


def test_export_public_key(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    store = CredentialStore(db, tmp_path / "vault.key")
    store.set_master_password("master")
    keychain = Keychain(db, store)

    key = keychain.generate_key(key_type="ed25519", label="export-test")
    pub = keychain.export_public_key(key.id)
    assert pub is not None
    assert pub.startswith("ssh-ed25519")
    db.close()


def test_list_and_delete_keys(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    store = CredentialStore(db, tmp_path / "vault.key")
    store.set_master_password("master")
    keychain = Keychain(db, store)

    keychain.generate_key(key_type="ed25519", label="key-1")
    keychain.generate_key(key_type="ed25519", label="key-2")
    keys = keychain.list_keys()
    assert len(keys) == 2

    keychain.delete_key(keys[0].id)
    assert len(keychain.list_keys()) == 1
    db.close()


def test_paramiko_pkey_loading(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    store = CredentialStore(db, tmp_path / "vault.key")
    store.set_master_password("master")
    keychain = Keychain(db, store)

    key = keychain.generate_key(key_type="ed25519", label="paramiko-test")
    pkey = keychain.get_paramiko_pkey(key.id)
    assert pkey is not None
    db.close()
