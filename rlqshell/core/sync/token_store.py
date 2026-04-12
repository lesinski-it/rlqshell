"""Encrypted OAuth token persistence via the sync_state DB table."""

from __future__ import annotations

import json
import logging

from rlqshell.core.credential_store import CredentialStore
from rlqshell.core.database import Database

logger = logging.getLogger(__name__)


class SyncTokenStore:
    """Encrypt, store and retrieve OAuth tokens for cloud sync providers."""

    def __init__(self, db: Database, credential_store: CredentialStore) -> None:
        self._db = db
        self._cred = credential_store

    def save_tokens(
        self, provider: str, access_token: str, refresh_token: str
    ) -> None:
        """Encrypt and persist OAuth tokens for *provider*."""
        if not self._cred.is_unlocked:
            logger.warning("Vault locked — tokens not persisted")
            return
        payload = json.dumps({"access": access_token, "refresh": refresh_token})
        encrypted = self._cred.encrypt_password(payload)
        existing = self._db.fetchone(
            "SELECT id FROM sync_state WHERE provider = ?", (provider,)
        )
        if existing:
            self._db.execute(
                "UPDATE sync_state SET encrypted_tokens = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE provider = ?",
                (encrypted, provider),
            )
        else:
            self._db.execute(
                "INSERT INTO sync_state (provider, encrypted_tokens) VALUES (?, ?)",
                (provider, encrypted),
            )
        logger.info("Tokens saved for %s", provider)

    def load_tokens(self, provider: str) -> tuple[str, str] | None:
        """Load and decrypt stored tokens. Returns (access, refresh) or None."""
        if not self._cred.is_unlocked:
            return None
        row = self._db.fetchone(
            "SELECT encrypted_tokens FROM sync_state WHERE provider = ?", (provider,)
        )
        if not row or not row["encrypted_tokens"]:
            return None
        try:
            payload = self._cred.decrypt_password(bytes(row["encrypted_tokens"]))
            data = json.loads(payload)
            return (data["access"], data["refresh"])
        except Exception:
            logger.warning("Failed to decrypt tokens for %s", provider)
            return None

    def clear_tokens(self, provider: str) -> None:
        """Remove stored tokens for *provider*."""
        self._db.execute(
            "UPDATE sync_state SET encrypted_tokens = NULL WHERE provider = ?",
            (provider,),
        )
        logger.info("Tokens cleared for %s", provider)
