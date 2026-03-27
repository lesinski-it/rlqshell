"""Credential store — encrypted identity management with master password."""

from __future__ import annotations

import logging
from pathlib import Path

from cryptography.fernet import InvalidToken

from termplus.core.database import Database
from termplus.core.models.credential import Identity
from termplus.utils.crypto import decrypt, derive_key, encrypt, generate_salt

logger = logging.getLogger(__name__)

_VERIFICATION_TOKEN = b"TERMPLUS_VAULT_VERIFIED"


class CredentialStore:
    """Manages encrypted credentials with master password protection.

    The master password is used to derive a Fernet key via PBKDF2.
    A vault.key file stores the salt and an encrypted verification token
    so the password can be validated on unlock.
    """

    def __init__(self, db: Database, vault_key_path: Path) -> None:
        self._db = db
        self._vault_key_path = vault_key_path
        self._master_key: bytes | None = None

    @property
    def is_unlocked(self) -> bool:
        return self._master_key is not None

    @property
    def has_master_password(self) -> bool:
        """True if a master password has been set (vault.key exists)."""
        return self._vault_key_path.exists()

    def set_master_password(self, password: str) -> None:
        """Set (or change) the master password. Creates vault.key."""
        salt = generate_salt()
        key = derive_key(password, salt)
        token = encrypt(_VERIFICATION_TOKEN, key)

        # vault.key format: salt (16 bytes) + encrypted verification token
        self._vault_key_path.write_bytes(salt + token)
        self._master_key = key
        logger.info("Master password set")

    def unlock(self, password: str) -> bool:
        """Unlock the vault with the master password. Returns True on success."""
        if not self._vault_key_path.exists():
            return False

        data = self._vault_key_path.read_bytes()
        salt = data[:16]
        token = data[16:]

        key = derive_key(password, salt)
        try:
            result = decrypt(token, key)
            if result == _VERIFICATION_TOKEN:
                self._master_key = key
                logger.info("Vault unlocked")
                return True
        except InvalidToken:
            pass

        logger.warning("Failed to unlock vault — wrong password")
        return False

    def lock(self) -> None:
        """Lock the vault — clear the master key from memory."""
        self._master_key = None
        logger.info("Vault locked")

    def encrypt_password(self, plaintext: str) -> bytes:
        """Encrypt a password string. Requires unlocked vault."""
        if self._master_key is None:
            raise RuntimeError("Vault is locked — cannot encrypt")
        return encrypt(plaintext.encode("utf-8"), self._master_key)

    def decrypt_password(self, ciphertext: bytes) -> str:
        """Decrypt a password blob. Requires unlocked vault."""
        if self._master_key is None:
            raise RuntimeError("Vault is locked — cannot decrypt")
        return decrypt(ciphertext, self._master_key).decode("utf-8")

    # --- Identity CRUD ---

    def create_identity(
        self,
        label: str,
        username: str,
        auth_type: str = "password",
        password: str | None = None,
        ssh_key_id: int | None = None,
        vault_id: int = 1,
    ) -> int:
        """Create an identity with optional encrypted password."""
        encrypted = None
        if password and self._master_key:
            encrypted = self.encrypt_password(password)

        cursor = self._db.execute(
            """INSERT INTO identities
                (vault_id, label, username, auth_type, encrypted_password, ssh_key_id)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (vault_id, label, username, auth_type, encrypted, ssh_key_id),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    def get_identity(self, identity_id: int) -> Identity | None:
        """Fetch an identity by id."""
        row = self._db.fetchone("SELECT * FROM identities WHERE id=?", (identity_id,))
        if row is None:
            return None
        return Identity(
            id=row["id"],
            vault_id=row["vault_id"],
            label=row["label"],
            username=row["username"],
            auth_type=row["auth_type"],
            encrypted_password=row["encrypted_password"],
            ssh_key_id=row["ssh_key_id"],
            created_at=row["created_at"],
        )

    def get_decrypted_password(self, identity_id: int) -> str | None:
        """Get the decrypted password for an identity."""
        identity = self.get_identity(identity_id)
        if identity is None or identity.encrypted_password is None:
            return None
        return self.decrypt_password(identity.encrypted_password)

    def list_identities(self, vault_id: int = 1) -> list[Identity]:
        """List all identities in a vault."""
        rows = self._db.fetchall(
            "SELECT * FROM identities WHERE vault_id=? ORDER BY label",
            (vault_id,),
        )
        return [
            Identity(
                id=r["id"], vault_id=r["vault_id"], label=r["label"],
                username=r["username"], auth_type=r["auth_type"],
                encrypted_password=r["encrypted_password"],
                ssh_key_id=r["ssh_key_id"], created_at=r["created_at"],
            )
            for r in rows
        ]

    def delete_identity(self, identity_id: int) -> None:
        """Delete an identity."""
        self._db.execute("DELETE FROM identities WHERE id=?", (identity_id,))
