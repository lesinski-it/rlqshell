"""Credential store — encrypted identity management with master password."""

from __future__ import annotations

import logging
import struct
from pathlib import Path

from cryptography.fernet import InvalidToken

from termplus.core.database import Database
from termplus.core.models.credential import Identity
from termplus.utils.crypto import (
    decrypt,
    derive_key,
    encrypt,
    generate_recovery_code,
    generate_salt,
)

logger = logging.getLogger(__name__)

_VERIFICATION_TOKEN = b"TERMPLUS_VAULT_VERIFIED"

# vault.key v2 magic: 4 ASCII chars + version byte
_VAULT_MAGIC = b"TPVK\x02"


class CredentialStore:
    """Manages encrypted credentials with master password protection.

    The master password is used to derive a Fernet key via PBKDF2.
    A vault.key file stores the salt and an encrypted verification token
    so the password can be validated on unlock.

    vault.key formats
    -----------------
    v1 (legacy): salt[16] + Fernet-token[N]
    v2: magic[5] + password_salt[16] + token_len[2] + token[N]
                 + recovery_salt[16] + enc_key_len[2] + enc_master_key[M]
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

    @property
    def has_recovery(self) -> bool:
        """True if vault.key is v2 format (supports recovery code)."""
        if not self._vault_key_path.exists():
            return False
        data = self._vault_key_path.read_bytes()
        return data[:5] == _VAULT_MAGIC

    def set_master_password(self, password: str) -> str:
        """Set the master password. Creates vault.key in v2 format.

        Returns the recovery code (shown to user once, not stored).
        """
        salt = generate_salt()
        key = derive_key(password, salt)
        token = encrypt(_VERIFICATION_TOKEN, key)

        recovery_code = generate_recovery_code()
        recovery_salt = generate_salt()
        recovery_key = derive_key(recovery_code.replace("-", ""), recovery_salt)
        enc_master_key = encrypt(key, recovery_key)

        self._vault_key_path.write_bytes(
            self._pack_v2(salt, token, recovery_salt, enc_master_key)
        )
        self._master_key = key
        logger.info("Master password set (v2 format with recovery)")
        return recovery_code

    def unlock(self, password: str) -> bool:
        """Unlock the vault with the master password. Returns True on success."""
        if not self._vault_key_path.exists():
            return False

        data = self._vault_key_path.read_bytes()

        if data[:5] == _VAULT_MAGIC:
            return self._unlock_v2(password, data)
        return self._unlock_v1(password, data)

    def lock(self) -> None:
        """Lock the vault — clear the master key from memory."""
        self._master_key = None
        logger.info("Vault locked")

    def change_master_password(self, old_password: str, new_password: str) -> str:
        """Change the master password and re-encrypt all stored credentials.

        Returns the new recovery code (shown to user once, not stored).
        Raises ValueError if old_password is wrong.
        """
        if not self.unlock(old_password):
            raise ValueError("Wrong current password")
        old_key = self._master_key
        assert old_key is not None
        return self._rekey(old_key, new_password)

    def recover_with_code(self, recovery_code: str, new_password: str) -> str:
        """Recover vault access using the recovery code.

        Re-encrypts all data with new_password and generates a new recovery code.
        Returns the new recovery code.
        Raises ValueError if vault format is v1 (no recovery data) or code is wrong.
        """
        if not self._vault_key_path.exists():
            raise ValueError("No vault found")

        data = self._vault_key_path.read_bytes()
        if data[:5] != _VAULT_MAGIC:
            raise ValueError(
                "Recovery not available for this vault. "
                "Change the password while logged in to enable recovery."
            )

        offset = 5
        _password_salt = data[offset : offset + 16]
        offset += 16
        token_len = struct.unpack_from(">H", data, offset)[0]
        offset += 2
        token = data[offset : offset + token_len]
        offset += token_len
        recovery_salt = data[offset : offset + 16]
        offset += 16
        enc_key_len = struct.unpack_from(">H", data, offset)[0]
        offset += 2
        enc_master_key = data[offset : offset + enc_key_len]

        normalized = recovery_code.replace("-", "").replace(" ", "").upper()
        recovery_key = derive_key(normalized, recovery_salt)
        try:
            old_key = decrypt(enc_master_key, recovery_key)
        except InvalidToken:
            raise ValueError("Invalid recovery code")

        # Sanity-check: verify the recovered key decrypts the verification token
        try:
            result = decrypt(token, old_key)
            if result != _VERIFICATION_TOKEN:
                raise ValueError("Recovery code mismatch")
        except InvalidToken:
            raise ValueError("Invalid recovery code")

        logger.info("Vault recovery successful, rekeying")
        return self._rekey(old_key, new_password)

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
                id=r["id"],
                vault_id=r["vault_id"],
                label=r["label"],
                username=r["username"],
                auth_type=r["auth_type"],
                encrypted_password=r["encrypted_password"],
                ssh_key_id=r["ssh_key_id"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def delete_identity(self, identity_id: int) -> None:
        """Delete an identity."""
        self._db.execute("DELETE FROM identities WHERE id=?", (identity_id,))

    # --- Private helpers ---

    def _unlock_v1(self, password: str, data: bytes) -> bool:
        """Unlock v1 vault.key format."""
        salt = data[:16]
        token = data[16:]
        key = derive_key(password, salt)
        try:
            result = decrypt(token, key)
            if result == _VERIFICATION_TOKEN:
                self._master_key = key
                logger.info("Vault unlocked (v1 format)")
                return True
        except InvalidToken:
            pass
        logger.warning("Failed to unlock vault — wrong password")
        return False

    def _unlock_v2(self, password: str, data: bytes) -> bool:
        """Unlock v2 vault.key format."""
        offset = 5
        salt = data[offset : offset + 16]
        offset += 16
        token_len = struct.unpack_from(">H", data, offset)[0]
        offset += 2
        token = data[offset : offset + token_len]

        key = derive_key(password, salt)
        try:
            result = decrypt(token, key)
            if result == _VERIFICATION_TOKEN:
                self._master_key = key
                logger.info("Vault unlocked (v2 format)")
                return True
        except InvalidToken:
            pass
        logger.warning("Failed to unlock vault — wrong password")
        return False

    def _rekey(self, old_key: bytes, new_password: str) -> str:
        """Re-encrypt all credentials with a new password, update vault.key.

        Returns the new recovery code.
        """
        new_salt = generate_salt()
        new_key = derive_key(new_password, new_salt)

        with self._db.connection() as conn:
            # Re-encrypt identity passwords
            rows = conn.execute(
                "SELECT id, encrypted_password FROM identities"
                " WHERE encrypted_password IS NOT NULL"
            ).fetchall()
            for row in rows:
                plaintext = self._try_decrypt(bytes(row["encrypted_password"]), old_key)
                conn.execute(
                    "UPDATE identities SET encrypted_password=? WHERE id=?",
                    (encrypt(plaintext, new_key), row["id"]),
                )

            # Re-encrypt SSH keys
            rows = conn.execute(
                "SELECT id, encrypted_private_key, encrypted_passphrase FROM ssh_keys"
            ).fetchall()
            for row in rows:
                new_pk = (
                    encrypt(self._try_decrypt(bytes(row["encrypted_private_key"]), old_key), new_key)
                    if row["encrypted_private_key"]
                    else None
                )
                new_pp = (
                    encrypt(self._try_decrypt(bytes(row["encrypted_passphrase"]), old_key), new_key)
                    if row["encrypted_passphrase"]
                    else None
                )
                conn.execute(
                    "UPDATE ssh_keys SET encrypted_private_key=?,"
                    " encrypted_passphrase=? WHERE id=?",
                    (new_pk, new_pp, row["id"]),
                )
            conn.commit()

        # Write new vault.key in v2 format
        new_token = encrypt(_VERIFICATION_TOKEN, new_key)
        recovery_code = generate_recovery_code()
        recovery_salt = generate_salt()
        recovery_key = derive_key(recovery_code.replace("-", ""), recovery_salt)
        enc_master_key = encrypt(new_key, recovery_key)

        self._vault_key_path.write_bytes(
            self._pack_v2(new_salt, new_token, recovery_salt, enc_master_key)
        )
        self._master_key = new_key
        logger.info("Vault rekeyed successfully")
        return recovery_code

    @staticmethod
    def _try_decrypt(data: bytes, key: bytes) -> bytes:
        """Decrypt data with key; if InvalidToken, return data as-is (was unencrypted).

        Handles the case where SSH keys or passwords were stored unencrypted
        because the vault was locked at the time of storage.
        """
        try:
            return decrypt(data, key)
        except InvalidToken:
            logger.warning(
                "Data appears unencrypted (stored while vault was locked) — "
                "treating as plaintext for re-encryption"
            )
            return data

    @staticmethod
    def _pack_v2(
        password_salt: bytes,
        token: bytes,
        recovery_salt: bytes,
        enc_master_key: bytes,
    ) -> bytes:
        """Serialise vault.key in v2 binary format."""
        return (
            _VAULT_MAGIC
            + password_salt
            + struct.pack(">H", len(token))
            + token
            + recovery_salt
            + struct.pack(">H", len(enc_master_key))
            + enc_master_key
        )
