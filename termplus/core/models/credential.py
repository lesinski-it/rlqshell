"""Identity / credential data model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Identity:
    """An authentication identity (username + auth method)."""

    id: int | None = None
    vault_id: int = 1
    label: str = ""
    username: str = ""
    auth_type: str = "password"  # password | key | key+passphrase | agent
    encrypted_password: bytes | None = None
    ssh_key_id: int | None = None
    created_at: datetime | None = None
