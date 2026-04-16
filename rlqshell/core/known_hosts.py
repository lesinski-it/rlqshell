"""Known hosts manager — server fingerprint verification."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from rlqshell.core.database import Database

logger = logging.getLogger(__name__)


class HostKeyStatus(Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    NOT_FOUND = "not_found"


class KnownHostsManager:
    """CRUD and verification of known host SSH fingerprints."""

    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    def _new_sync_uuid() -> str:
        return str(uuid4())

    def _record_tombstone(self, sync_uuid: str | None) -> None:
        if not sync_uuid:
            return
        deleted_at = datetime.now(tz=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        self._db.execute(
            "INSERT OR REPLACE INTO sync_tombstones"
            " (entity_type, sync_uuid, deleted_at) VALUES (?, ?, ?)",
            ("known_hosts", sync_uuid, deleted_at),
        )

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
        """Store or update a host key, preserving sync_uuid on update."""
        existing = self._db.fetchone(
            "SELECT id, sync_uuid FROM known_hosts WHERE hostname=? AND port=?",
            (hostname, port),
        )
        if existing:
            self._db.execute(
                """UPDATE known_hosts SET key_type=?, host_key=?, fingerprint=?,
                   last_seen=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                WHERE id=?""",
                (key_type, host_key, fingerprint, existing["id"]),
            )
        else:
            sync_uuid = self._new_sync_uuid()
            self._db.execute(
                """INSERT INTO known_hosts
                    (hostname, port, key_type, host_key, fingerprint, sync_uuid)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (hostname, port, key_type, host_key, fingerprint, sync_uuid),
            )
        logger.info("Added/updated known host: %s:%d (%s)", hostname, port, key_type)

    def remove_host_key(self, hostname: str, port: int) -> None:
        """Remove a known host entry."""
        row = self._db.fetchone(
            "SELECT sync_uuid FROM known_hosts WHERE hostname=? AND port=?",
            (hostname, port),
        )
        self._record_tombstone(row["sync_uuid"] if row else None)
        self._db.execute(
            "DELETE FROM known_hosts WHERE hostname=? AND port=?",
            (hostname, port),
        )

    def delete_by_id(self, entry_id: int) -> None:
        """Delete a known host by database ID."""
        row = self._db.fetchone(
            "SELECT sync_uuid FROM known_hosts WHERE id=?", (entry_id,)
        )
        self._record_tombstone(row["sync_uuid"] if row else None)
        self._db.execute("DELETE FROM known_hosts WHERE id=?", (entry_id,))

    def list_all(self) -> list[dict]:
        """List all known hosts."""
        rows = self._db.fetchall(
            "SELECT * FROM known_hosts ORDER BY hostname", ()
        )
        return [dict(r) for r in rows]
