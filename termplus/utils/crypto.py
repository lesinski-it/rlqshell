"""Encryption utilities using Fernet (AES-256) with PBKDF2 key derivation."""

from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def generate_salt() -> bytes:
    """Generate a random 16-byte salt."""
    return os.urandom(16)


def derive_key(password: str, salt: bytes) -> bytes:
    """Derive a Fernet-compatible key from a password using PBKDF2.

    Returns a 44-byte base64-encoded key suitable for Fernet.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,
    )
    raw_key = kdf.derive(password.encode("utf-8"))
    return base64.urlsafe_b64encode(raw_key)


def encrypt(data: bytes, key: bytes) -> bytes:
    """Encrypt data using Fernet."""
    f = Fernet(key)
    return f.encrypt(data)


def decrypt(data: bytes, key: bytes) -> bytes:
    """Decrypt data using Fernet. Raises InvalidToken on failure."""
    f = Fernet(key)
    return f.decrypt(data)


def generate_fernet_key() -> bytes:
    """Generate a random Fernet key."""
    return Fernet.generate_key()
