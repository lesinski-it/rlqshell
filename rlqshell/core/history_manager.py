"""Connection and command history management."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from rlqshell.core.database import Database

logger = logging.getLogger(__name__)


@dataclass
class ConnectionRecord:
    id: int | None = None
    host_id: int | None = None
    host_label: str = ""
    address: str = ""
    protocol: str = "ssh"
    connected_at: str | None = None
    disconnected_at: str | None = None
    duration_seconds: int | None = None
    sync_uuid: str | None = None
    updated_at: str | None = None


class HistoryManager:
    """Records and queries connection and command history."""

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
            ("connection_history", sync_uuid, deleted_at),
        )

    # --- Connection History ---

    def record_connect(
        self, host_id: int | None, host_label: str, address: str, protocol: str = "ssh",
    ) -> int:
        """Record a new connection. Returns the history record id."""
        sync_uuid = self._new_sync_uuid()
        cursor = self._db.execute(
            """INSERT INTO connection_history
               (host_id, host_label, address, protocol, sync_uuid)
            VALUES (?, ?, ?, ?, ?)""",
            (host_id, host_label, address, protocol, sync_uuid),
        )
        record_id = cursor.lastrowid
        logger.debug("Recorded connection start: %s (%s)", host_label, address)
        return record_id  # type: ignore[return-value]

    def record_disconnect(self, record_id: int) -> None:
        """Update a connection record with disconnection time and duration."""
        self._db.execute(
            """UPDATE connection_history SET
                disconnected_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP,
                duration_seconds = CAST(
                    (julianday(CURRENT_TIMESTAMP) - julianday(connected_at)) * 86400
                    AS INTEGER
                )
            WHERE id = ?""",
            (record_id,),
        )

    def list_connections(
        self, limit: int = 100, search: str | None = None,
    ) -> list[ConnectionRecord]:
        """List recent connection history."""
        sql = "SELECT * FROM connection_history"
        params: list = []

        if search:
            sql += " WHERE host_label LIKE ? OR address LIKE ?"
            like = f"%{search}%"
            params.extend([like, like])

        sql += " ORDER BY connected_at DESC LIMIT ?"
        params.append(limit)

        rows = self._db.fetchall(sql, tuple(params))
        return [
            ConnectionRecord(
                id=r["id"],
                host_id=r["host_id"],
                host_label=r["host_label"] or "",
                address=r["address"] or "",
                protocol=r["protocol"] or "ssh",
                connected_at=r["connected_at"],
                disconnected_at=r["disconnected_at"],
                duration_seconds=r["duration_seconds"],
                sync_uuid=r["sync_uuid"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def clear_history(self) -> None:
        """Delete all connection history, recording tombstones for sync."""
        rows = self._db.fetchall(
            "SELECT sync_uuid FROM connection_history WHERE sync_uuid IS NOT NULL", ()
        )
        for row in rows:
            self._record_tombstone(row["sync_uuid"])
        self._db.execute("DELETE FROM connection_history")

    # --- Command History ---

    def record_command(self, host_id: int | None, command: str) -> None:
        """Record a command execution."""
        self._db.execute(
            "INSERT INTO command_history (host_id, command) VALUES (?, ?)",
            (host_id, command),
        )

    def list_commands(self, host_id: int | None = None, limit: int = 100) -> list[dict]:
        """List recent commands, optionally filtered by host."""
        if host_id is not None:
            rows = self._db.fetchall(
                "SELECT * FROM command_history WHERE host_id=? ORDER BY executed_at DESC LIMIT ?",
                (host_id, limit),
            )
        else:
            rows = self._db.fetchall(
                "SELECT * FROM command_history ORDER BY executed_at DESC LIMIT ?",
                (limit,),
            )
        return [dict(r) for r in rows]
