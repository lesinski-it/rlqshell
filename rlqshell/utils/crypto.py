"""Encryption utilities using Fernet (AES-256) with PBKDF2 key derivation."""

from __future__ import annotations

import base64
import os
import secrets
import string

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


def generate_recovery_code() -> str:
    """Generate a random 25-character recovery code.

    Format: XXXXX-XXXXX-XXXXX-XXXXX-XXXXX (5 groups of 5, uppercase alphanumeric).
    Excludes visually ambiguous characters: O, 0, I, 1.
    """
    alphabet = "".join(
        c for c in (string.ascii_uppercase + string.digits) if c not in "O0I1"
    )
    code = "".join(secrets.choice(alphabet) for _ in range(25))
    return "-".join(code[i : i + 5] for i in range(0, 25, 5))
