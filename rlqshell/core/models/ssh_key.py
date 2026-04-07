"""SSH key data model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class SSHKey:
    """An SSH key pair stored in the vault."""

    id: int | None = None
    vault_id: int = 1
    label: str = ""
    key_type: str = "ed25519"  # rsa | ed25519 | ecdsa | rsa-cert | ed25519-cert
    encrypted_private_key: bytes | None = None
    public_key: str | None = None
    encrypted_passphrase: bytes | None = None
    fingerprint: str | None = None
    bits: int | None = None
    created_at: datetime | None = None
