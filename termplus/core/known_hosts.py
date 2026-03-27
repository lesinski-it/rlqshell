"""Known hosts manager — server fingerprint verification."""

from __future__ import annotations

import logging
from enum import Enum

from termplus.core.database import Database

logger = logging.getLogger(__name__)


class HostKeyStatus(Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    NOT_FOUND = "not_found"


class KnownHostsManager:
    """CRUD and verification of known host SSH fingerprints."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def verify_host_key(
        self, hostname: str, port: int, key_type: str, fingerprint: str
    ) -> HostKeyStatus:
        """Check if a host's key matches our records."""
        row = self._db.fetchone(
            "SELECT fingerprint FROM known_hosts WHERE hostname=? AND port=?",
            (hostname, port),
        )
        if row is None:
            return HostKeyStatus.NOT_FOUND
        if row["fingerprint"] == fingerprint:
            return HostKeyStatus.MATCH
        return HostKeyStatus.MISMATCH

    def add_host_key(
        self,
        hostname: str,
        port: int,
        key_type: str,
        fingerprint: str,
        host_key: str = "",
    ) -> None:
        """Store a new host key."""
        self._db.execute(
            """INSERT OR REPLACE INTO known_hosts
                (hostname, port, key_type, host_key, fingerprint)
            VALUES (?, ?, ?, ?, ?)""",
            (hostname, port, key_type, host_key, fingerprint),
        )
        logger.info("Added known host: %s:%d (%s)", hostname, port, key_type)

    def remove_host_key(self, hostname: str, port: int) -> None:
        """Remove a known host entry."""
        self._db.execute(
            "DELETE FROM known_hosts WHERE hostname=? AND port=?",
            (hostname, port),
        )

    def delete_by_id(self, entry_id: int) -> None:
        """Delete a known host by database ID."""
        self._db.execute("DELETE FROM known_hosts WHERE id=?", (entry_id,))

    def list_all(self) -> list[dict]:
        """List all known hosts."""
        rows = self._db.fetchall(
            "SELECT * FROM known_hosts ORDER BY hostname", ()
        )
        return [dict(r) for r in rows]
