"""SSH key management — generate, import, export."""

from __future__ import annotations

import base64
import hashlib
import logging
from datetime import UTC, datetime
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa

from rlqshell.core.credential_store import CredentialStore
from rlqshell.core.database import Database
from rlqshell.core.models.ssh_key import SSHKey

logger = logging.getLogger(__name__)


class Keychain:
    """SSH key management: generate, import, export, and store."""

    def __init__(self, db: Database, credential_store: CredentialStore) -> None:
        self._db = db
        self._cred_store = credential_store

    def generate_key(
        self,
        key_type: str = "ed25519",
        bits: int = 4096,
        passphrase: str | None = None,
        label: str = "",
        vault_id: int = 1,
    ) -> SSHKey:
        """Generate a new SSH key pair and store it in the database."""
        private_key, key_bits = self._generate_private_key(key_type, bits)

        # Serialize private key to PEM
        encryption = (
            serialization.BestAvailableEncryption(passphrase.encode())
            if passphrase
            else serialization.NoEncryption()
        )
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.OpenSSH,
            encryption_algorithm=encryption,
        )

        # Public key in OpenSSH format
        public_key_str = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        ).decode("utf-8")

        # Fingerprint
        fingerprint = self._compute_fingerprint(private_key.public_key())

        # Encrypt private key and passphrase for DB storage
        encrypted_private = self._encrypt_bytes(private_pem)
        encrypted_passphrase = None
        if passphrase and self._cred_store.is_unlocked:
            encrypted_passphrase = self._cred_store.encrypt_password(passphrase)

        sync_uuid = str(uuid4())
        cursor = self._db.execute(
            """INSERT INTO ssh_keys
                (vault_id, label, key_type, encrypted_private_key, public_key,
                 encrypted_passphrase, fingerprint, bits, sync_uuid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (vault_id, label, key_type, encrypted_private, public_key_str,
             encrypted_passphrase, fingerprint, key_bits, sync_uuid),
        )

        return SSHKey(
            id=cursor.lastrowid,
            vault_id=vault_id,
            label=label,
            key_type=key_type,
            encrypted_private_key=encrypted_private,
            public_key=public_key_str,
            encrypted_passphrase=encrypted_passphrase,
            fingerprint=fingerprint,
            bits=key_bits,
            sync_uuid=sync_uuid,
        )

    def import_key(
        self,
        private_key_pem: bytes,
        passphrase: str | None = None,
        label: str = "",
        vault_id: int = 1,
    ) -> SSHKey:
        """Import an existing private key from PEM data."""
        pwd = passphrase.encode() if passphrase else None
        private_key = serialization.load_pem_private_key(private_key_pem, password=pwd)

        # Determine key type and bits
        if isinstance(private_key, ed25519.Ed25519PrivateKey):
            key_type, key_bits = "ed25519", 256
        elif isinstance(private_key, rsa.RSAPrivateKey):
            key_type, key_bits = "rsa", private_key.key_size
        elif isinstance(private_key, ec.EllipticCurvePrivateKey):
            key_type, key_bits = "ecdsa", private_key.key_size
        else:
            raise ValueError(f"Unsupported key type: {type(private_key)}")

        public_key_str = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        ).decode("utf-8")

        fingerprint = self._compute_fingerprint(private_key.public_key())
        encrypted_private = self._encrypt_bytes(private_key_pem)
        encrypted_passphrase = None
        if passphrase and self._cred_store.is_unlocked:
            encrypted_passphrase = self._cred_store.encrypt_password(passphrase)

        sync_uuid = str(uuid4())
        cursor = self._db.execute(
            """INSERT INTO ssh_keys
                (vault_id, label, key_type, encrypted_private_key, public_key,
                 encrypted_passphrase, fingerprint, bits, sync_uuid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (vault_id, label, key_type, encrypted_private, public_key_str,
             encrypted_passphrase, fingerprint, key_bits, sync_uuid),
        )

        return SSHKey(
            id=cursor.lastrowid, vault_id=vault_id, label=label,
            key_type=key_type, encrypted_private_key=encrypted_private,
            public_key=public_key_str, encrypted_passphrase=encrypted_passphrase,
            fingerprint=fingerprint, bits=key_bits, sync_uuid=sync_uuid,
        )

    def export_public_key(self, key_id: int) -> str | None:
        """Return the public key string for a stored key."""
        row = self._db.fetchone("SELECT public_key FROM ssh_keys WHERE id=?", (key_id,))
        return row["public_key"] if row else None

    def export_private_key(self, key_id: int) -> bytes | None:
        """Decrypt and return the private key PEM."""
        row = self._db.fetchone(
            "SELECT encrypted_private_key FROM ssh_keys WHERE id=?", (key_id,)
        )
        if row is None or row["encrypted_private_key"] is None:
            return None
        return self._decrypt_bytes(row["encrypted_private_key"])

    def get_paramiko_pkey(self, key_id: int):
        """Load a stored key as a paramiko PKey instance."""
        import paramiko

        pem = self.export_private_key(key_id)
        if pem is None:
            return None

        # Get passphrase if any
        row = self._db.fetchone(
            "SELECT encrypted_passphrase FROM ssh_keys WHERE id=?", (key_id,)
        )
        passphrase = None
        if row and row["encrypted_passphrase"] and self._cred_store.is_unlocked:
            passphrase = self._cred_store.decrypt_password(row["encrypted_passphrase"])

        pwd = passphrase.encode() if passphrase else None
        return paramiko.RSAKey.from_private_key_file(
            None,  # not from file
        ) if False else self._load_paramiko_from_pem(pem, pwd)

    def delete_key(self, key_id: int) -> None:
        """Delete an SSH key."""
        row = self._db.fetchone("SELECT sync_uuid FROM ssh_keys WHERE id=?", (key_id,))
        if row and row["sync_uuid"]:
            deleted_at = (
                datetime.now(tz=UTC)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
            self._db.execute(
                "INSERT OR REPLACE INTO sync_tombstones"
                " (entity_type, sync_uuid, deleted_at) VALUES (?, ?, ?)",
                ("ssh_keys", row["sync_uuid"], deleted_at),
            )
        self._db.execute("DELETE FROM ssh_keys WHERE id=?", (key_id,))

    def list_keys(self, vault_id: int = 1) -> list[SSHKey]:
        """List all SSH keys in a vault."""
        rows = self._db.fetchall(
            "SELECT * FROM ssh_keys WHERE vault_id=? ORDER BY label",
            (vault_id,),
        )
        return [
            SSHKey(
                id=r["id"], vault_id=r["vault_id"], label=r["label"],
                key_type=r["key_type"], public_key=r["public_key"],
                fingerprint=r["fingerprint"], bits=r["bits"],
                sync_uuid=r["sync_uuid"],
                created_at=r["created_at"], updated_at=r["updated_at"],
            )
            for r in rows
        ]

    # --- Private ---

    @staticmethod
    def _generate_private_key(key_type: str, bits: int):
        if key_type == "ed25519":
            return ed25519.Ed25519PrivateKey.generate(), 256
        elif key_type == "rsa":
            return rsa.generate_private_key(65537, bits), bits
        elif key_type == "ecdsa":
            curve = ec.SECP256R1() if bits <= 256 else ec.SECP384R1()
            return ec.generate_private_key(curve), bits
        raise ValueError(f"Unsupported key type: {key_type}")

    @staticmethod
    def _compute_fingerprint(public_key) -> str:
        raw = public_key.public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        )
        # Parse OpenSSH format: type + base64 data
        parts = raw.split(b" ", 2)
        key_data = base64.b64decode(parts[1]) if len(parts) >= 2 else raw
        digest = hashlib.sha256(key_data).digest()
        return "SHA256:" + base64.b64encode(digest).rstrip(b"=").decode("ascii")

    def _encrypt_bytes(self, data: bytes) -> bytes:
        if self._cred_store.is_unlocked:
            from rlqshell.utils.crypto import encrypt
            return encrypt(data, self._cred_store._master_key)  # type: ignore[arg-type]
        return data  # fallback: store unencrypted if no master password

    def _decrypt_bytes(self, data: bytes) -> bytes:
        if self._cred_store.is_unlocked:
            from rlqshell.utils.crypto import decrypt
            return decrypt(data, self._cred_store._master_key)  # type: ignore[arg-type]
        return data

    @staticmethod
    def _load_paramiko_from_pem(pem: bytes, password: bytes | None):
        """Load a PEM-encoded private key into a paramiko PKey."""
        import io
        import paramiko

        pwd_str = password.decode() if password else None
        pem_str = pem.decode("utf-8")

        for key_class in [paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey]:
            try:
                return key_class.from_private_key(io.StringIO(pem_str), password=pwd_str)
            except Exception:
                continue
        raise ValueError("Could not load key with paramiko — unsupported format")
