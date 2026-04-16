"""Port forwarding rule CRUD manager."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from rlqshell.core.database import Database

logger = logging.getLogger(__name__)


@dataclass
class PortForwardRule:
    id: int | None = None
    vault_id: int = 1
    host_id: int = 0
    label: str = ""
    direction: str = "local"  # local, remote, dynamic
    bind_address: str = "127.0.0.1"
    local_port: int = 0
    remote_host: str = ""
    remote_port: int | None = None
    auto_start: bool = True
    created_at: str | None = None
    sync_uuid: str | None = None
    updated_at: str | None = None


class PortForwardManager:
    """CRUD operations for port forwarding rules."""

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
            ("port_forward_rules", sync_uuid, deleted_at),
        )

    def create_rule(self, rule: PortForwardRule) -> int:
        sync_uuid = rule.sync_uuid or self._new_sync_uuid()
        cursor = self._db.execute(
            """INSERT INTO port_forward_rules
                (vault_id, host_id, label, direction, bind_address,
                 local_port, remote_host, remote_port, auto_start,
                 sync_uuid, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (
                rule.vault_id, rule.host_id, rule.label, rule.direction,
                rule.bind_address, rule.local_port, rule.remote_host,
                rule.remote_port, rule.auto_start, sync_uuid,
            ),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    def update_rule(self, rule: PortForwardRule) -> None:
        self._db.execute(
            """UPDATE port_forward_rules SET
                host_id=?, label=?, direction=?, bind_address=?,
                local_port=?, remote_host=?, remote_port=?, auto_start=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?""",
            (
                rule.host_id, rule.label, rule.direction, rule.bind_address,
                rule.local_port, rule.remote_host, rule.remote_port,
                rule.auto_start, rule.id,
            ),
        )

    def delete_rule(self, rule_id: int) -> None:
        row = self._db.fetchone(
            "SELECT sync_uuid FROM port_forward_rules WHERE id=?", (rule_id,)
        )
        self._record_tombstone(row["sync_uuid"] if row else None)
        self._db.execute("DELETE FROM port_forward_rules WHERE id=?", (rule_id,))

    def get_rule(self, rule_id: int) -> PortForwardRule | None:
        row = self._db.fetchone(
            "SELECT * FROM port_forward_rules WHERE id=?", (rule_id,),
        )
        if row is None:
            return None
        return self._row_to_rule(row)

    def list_rules(self, host_id: int | None = None) -> list[PortForwardRule]:
        if host_id is not None:
            rows = self._db.fetchall(
                "SELECT * FROM port_forward_rules WHERE host_id=? ORDER BY label",
                (host_id,),
            )
        else:
            rows = self._db.fetchall(
                "SELECT * FROM port_forward_rules ORDER BY label", (),
            )
        return [self._row_to_rule(r) for r in rows]

    @staticmethod
    def _row_to_rule(row) -> PortForwardRule:
        return PortForwardRule(
            id=row["id"],
            vault_id=row["vault_id"],
            host_id=row["host_id"],
            label=row["label"] or "",
            direction=row["direction"],
            bind_address=row["bind_address"] or "127.0.0.1",
            local_port=row["local_port"],
            remote_host=row["remote_host"] or "",
            remote_port=row["remote_port"],
            auto_start=bool(row["auto_start"]),
            created_at=row["created_at"],
            sync_uuid=row["sync_uuid"],
            updated_at=row["updated_at"],
        )
