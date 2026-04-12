"""Sync engine — orchestrates pull/merge/push to cloud storage."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiohttp
from PySide6.QtCore import QObject, QTimer, Signal

from rlqshell.app.constants import APP_VERSION
from rlqshell.core.database import Database
from rlqshell.core.sync.conflict_resolver import ConflictResolver
from rlqshell.core.sync.providers.base import AbstractCloudProvider
from rlqshell.core.sync.sync_state import SyncState

logger = logging.getLogger(__name__)

_SYNC_FILES = ["vault.key", "config.json"]
_SYNC_RECORDS_FILE = "sync_records_v2.json"
_TOMBSTONE_RETENTION_DAYS = 30

_BOOL_FIELDS = {
    "ssh_agent_forwarding",
    "ssh_x11_forwarding",
    "ssh_compression",
    "rdp_audio",
    "rdp_clipboard",
    "vnc_view_only",
    "telnet_raw_mode",
}

_HOST_FIELDS = [
    "vault_id",
    "label",
    "address",
    "protocol",
    "ssh_port",
    "ssh_identity_id",
    "ssh_startup_snippet_id",
    "ssh_keep_alive",
    "ssh_agent_forwarding",
    "ssh_x11_forwarding",
    "ssh_compression",
    "rdp_port",
    "rdp_username",
    "rdp_domain",
    "rdp_resolution",
    "rdp_color_depth",
    "rdp_audio",
    "rdp_clipboard",
    "rdp_drive_mapping",
    "vnc_port",
    "vnc_quality",
    "vnc_view_only",
    "telnet_port",
    "telnet_raw_mode",
    "serial_port_path",
    "serial_baud_rate",
    "serial_data_bits",
    "serial_stop_bits",
    "serial_parity",
    "serial_flow_control",
    "terminal_theme",
    "terminal_font",
    "terminal_font_size",
    "notes",
    "color_label",
    "sort_order",
]


class SyncEngine(QObject):
    """Orchestrates sync: pull → merge → push (per-file bidirectional)."""

    sync_started = Signal()
    sync_completed = Signal(dict)  # {"added": int, "updated": int, "deleted": int}
    sync_error = Signal(str)
    sync_conflict = Signal(str, str)  # filename, winner
    sync_skipped = Signal(str)  # reason

    def __init__(
        self,
        data_dir: Path,
        db: Database,
        sync_state: SyncState,
        conflict_resolver: ConflictResolver | None = None,
        cloud_folder: str = "/RLQShell",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._data_dir = data_dir
        self._db = db
        self._backups_dir = data_dir / "backups"
        self._state = sync_state
        self._resolver = conflict_resolver or ConflictResolver()
        self._cloud_folder = cloud_folder
        self._provider: AbstractCloudProvider | None = None
        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._on_auto_sync)
        self._syncing = False
        self._pending_sync = False
        self._token_save_callback = None

    @property
    def provider(self) -> AbstractCloudProvider | None:
        return self._provider

    @property
    def is_syncing(self) -> bool:
        return self._syncing

    @property
    def cloud_folder(self) -> str:
        return self._cloud_folder

    @cloud_folder.setter
    def cloud_folder(self, value: str) -> None:
        self._cloud_folder = value

    def set_provider(self, provider: AbstractCloudProvider) -> None:
        self._provider = provider
        self._state.set_provider(provider.provider_name)

    def set_token_save_callback(self, callback) -> None:
        """Set a callback to persist tokens after refresh. Signature: (str, str) -> None."""
        self._token_save_callback = callback

    def start_auto_sync(self, interval_minutes: int = 5) -> None:
        """Start periodic automatic sync."""
        self._auto_timer.start(interval_minutes * 60 * 1000)
        logger.info("Auto-sync enabled: every %d minutes", interval_minutes)

    def stop_auto_sync(self) -> None:
        self._auto_timer.stop()

    def _on_auto_sync(self) -> None:
        import asyncio

        asyncio.ensure_future(self.sync())

    async def _check_connectivity(self) -> bool:
        """Check if the cloud provider is reachable."""
        if self._provider is None:
            return False
        try:
            session = await self._provider._get_session()
            async with session.head(
                self._provider.connectivity_check_url,
                timeout=aiohttp.ClientTimeout(total=5),
                proxy=self._provider._proxy_url,
            ) as resp:
                return resp.status < 500
        except Exception:
            return False

    async def sync(self) -> None:
        """Execute one full sync cycle."""
        if self._provider is None or not self._provider.is_authenticated():
            logger.warning("Sync skipped - no provider or not authenticated")
            return

        if self._syncing:
            logger.warning("Sync already in progress")
            return

        if not await self._check_connectivity():
            logger.info("Sync skipped - offline")
            self._pending_sync = True
            self.sync_skipped.emit("offline")
            return

        self._syncing = True
        self._pending_sync = False
        self._state.status = "syncing"
        self.sync_started.emit()

        try:
            await self._provider.create_folder(self._cloud_folder)
            self._backup_local()

            self._prune_local_tombstones()
            sync_stats = await self._sync_records_v2()

            local_hashes: dict[str, str] = {
                "rlqshell.db": SyncState.compute_file_hash(self._data_dir / "rlqshell.db")
            }
            for filename in _SYNC_FILES:
                path = self._data_dir / filename
                local_hashes[filename] = SyncState.compute_file_hash(path)

            remote_meta = await self._get_remote_meta()
            remote_hashes: dict[str, str] = {}
            remote_modified: float | None = None

            if remote_meta:
                if remote_meta.get("file_hashes"):
                    remote_hashes = dict(remote_meta["file_hashes"])
                if remote_meta.get("last_modified"):
                    try:
                        remote_modified = datetime.fromisoformat(
                            str(remote_meta["last_modified"]).replace("Z", "+00:00")
                        ).timestamp()
                    except Exception:
                        remote_modified = None

            any_pushed = False
            any_pulled = False

            for filename in _SYNC_FILES:
                local_hash = local_hashes.get(filename, "")
                remote_hash = remote_hashes.get(filename, "")

                if local_hash == remote_hash:
                    continue

                local_path = self._data_dir / filename
                local_modified = local_path.stat().st_mtime if local_path.exists() else None

                if not remote_hash:
                    await self._push_file(filename)
                    any_pushed = True
                elif not local_hash:
                    await self._pull_file(filename)
                    any_pulled = True
                else:
                    winner = self._resolver.resolve(local_modified, remote_modified)
                    self.sync_conflict.emit(filename, winner)
                    if winner == "remote":
                        await self._pull_file(filename)
                        any_pulled = True
                    else:
                        await self._push_file(filename)
                        any_pushed = True

            if any_pulled:
                for filename in _SYNC_FILES:
                    local_hashes[filename] = SyncState.compute_file_hash(self._data_dir / filename)

            local_hashes["rlqshell.db"] = SyncState.compute_file_hash(self._data_dir / "rlqshell.db")

            records_changed = any(v > 0 for v in sync_stats.values())
            if any_pushed or any_pulled or records_changed or not remote_meta:
                meta = self._state.build_meta(
                    APP_VERSION,
                    local_hashes.get("rlqshell.db", ""),
                    local_hashes,
                )
                meta_json = json.dumps(asdict(meta), indent=2)
                meta_path = self._data_dir / "sync_meta.json"
                meta_path.write_text(meta_json, encoding="utf-8")
                await self._provider.upload_file(
                    str(meta_path),
                    f"{self._cloud_folder}/sync_meta.json",
                )

            if self._token_save_callback and self._provider:
                tokens = self._provider.get_tokens()
                if tokens:
                    self._token_save_callback(tokens[0], tokens[1])

            self._state.update_after_sync(
                local_hashes.get("rlqshell.db", ""),
                local_hashes.get("rlqshell.db", ""),
            )
            logger.info("Sync completed successfully")
            self.sync_completed.emit(sync_stats)

        except Exception as exc:
            logger.exception("Sync failed")
            self._state.status = "error"
            self.sync_error.emit(str(exc))
        finally:
            self._syncing = False

    async def _sync_records_v2(self) -> dict[str, int]:
        """Sync records and return stats: {added, updated, deleted, pushed}."""
        local_payload = self._sanitize_payload(self._export_local_records())
        remote_payload = self._sanitize_payload(await self._download_remote_records())
        merged_payload = self._merge_payloads(local_payload, remote_payload)

        stats: dict[str, int] = {
            "added": 0, "updated": 0, "deleted": 0, "pushed": 0,
        }
        if self._payload_hash(local_payload) != self._payload_hash(merged_payload):
            stats = self._apply_merged_payload(merged_payload)

        if self._payload_hash(remote_payload) != self._payload_hash(merged_payload):
            for entity in ("groups", "tags", "hosts", "host_tags"):
                remote_uuids = {
                    r["sync_uuid"] for r in remote_payload.get(entity, [])
                }
                for r in merged_payload.get(entity, []):
                    if r["sync_uuid"] not in remote_uuids:
                        stats["pushed"] += 1
            await self._upload_remote_records(merged_payload)

        return stats

    @staticmethod
    def _parse_ts(value: Any) -> datetime:
        if not value:
            return datetime.fromtimestamp(0, tz=timezone.utc)
        if isinstance(value, datetime):
            dt = value
        else:
            text = str(value).strip()
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                try:
                    dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    return datetime.fromtimestamp(0, tz=timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @classmethod
    def _normalize_ts(cls, value: Any) -> str:
        return cls._parse_ts(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _empty_payload() -> dict[str, Any]:
        return {
            "version": 2,
            "groups": [],
            "tags": [],
            "hosts": [],
            "host_tags": [],
            "tombstones": [],
        }

    @staticmethod
    def _payload_hash(payload: dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def _sanitize_payload(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return self._empty_payload()

        out = self._empty_payload()
        for key in ("groups", "tags", "hosts", "host_tags", "tombstones"):
            values = payload.get(key, [])
            if isinstance(values, list):
                out[key] = [v for v in values if isinstance(v, dict)]

        for entity in ("groups", "tags", "hosts", "host_tags"):
            normalized: list[dict[str, Any]] = []
            for rec in out[entity]:
                sync_uuid = str(rec.get("sync_uuid", "")).strip()
                if not sync_uuid:
                    continue
                item = dict(rec)
                item["sync_uuid"] = sync_uuid
                item["updated_at"] = self._normalize_ts(item.get("updated_at"))
                normalized.append(item)
            out[entity] = sorted(normalized, key=lambda r: r["sync_uuid"])

        normalized_tombstones: list[dict[str, Any]] = []
        for rec in out["tombstones"]:
            entity_type = str(rec.get("entity_type", "")).strip()
            sync_uuid = str(rec.get("sync_uuid", "")).strip()
            if not entity_type or not sync_uuid:
                continue
            normalized_tombstones.append(
                {
                    "entity_type": entity_type,
                    "sync_uuid": sync_uuid,
                    "deleted_at": self._normalize_ts(rec.get("deleted_at")),
                }
            )
        out["tombstones"] = sorted(
            normalized_tombstones,
            key=lambda r: (r["entity_type"], r["sync_uuid"]),
        )
        return out

    def _export_local_records(self) -> dict[str, Any]:
        payload = self._empty_payload()

        with self._db.connection() as conn:
            group_rows = conn.execute(
                """SELECT g.sync_uuid, g.name, g.icon, g.color, g.default_identity_id,
                          g.default_jump_host_id, g.sort_order, g.updated_at,
                          pg.sync_uuid AS parent_sync_uuid
                   FROM groups_ g
                   LEFT JOIN groups_ pg ON pg.id = g.parent_id
                   WHERE g.sync_uuid IS NOT NULL"""
            ).fetchall()
            for row in group_rows:
                payload["groups"].append(
                    {
                        "sync_uuid": row["sync_uuid"],
                        "parent_sync_uuid": row["parent_sync_uuid"],
                        "name": row["name"],
                        "icon": row["icon"],
                        "color": row["color"],
                        "default_identity_id": row["default_identity_id"],
                        "default_jump_host_id": row["default_jump_host_id"],
                        "sort_order": row["sort_order"],
                        "updated_at": self._normalize_ts(row["updated_at"]),
                    }
                )

            tag_rows = conn.execute(
                """SELECT sync_uuid, name, color, updated_at
                   FROM tags
                   WHERE sync_uuid IS NOT NULL"""
            ).fetchall()
            for row in tag_rows:
                payload["tags"].append(
                    {
                        "sync_uuid": row["sync_uuid"],
                        "name": row["name"],
                        "color": row["color"],
                        "updated_at": self._normalize_ts(row["updated_at"]),
                    }
                )

            host_rows = conn.execute(
                """SELECT h.*, g.sync_uuid AS group_sync_uuid,
                          chain.sync_uuid AS ssh_host_chain_sync_uuid
                   FROM hosts h
                   LEFT JOIN groups_ g ON g.id = h.group_id
                   LEFT JOIN hosts chain ON chain.id = h.ssh_host_chain_id
                   WHERE h.sync_uuid IS NOT NULL"""
            ).fetchall()
            for row in host_rows:
                record: dict[str, Any] = {
                    "sync_uuid": row["sync_uuid"],
                    "group_sync_uuid": row["group_sync_uuid"],
                    "ssh_host_chain_sync_uuid": row["ssh_host_chain_sync_uuid"],
                    "updated_at": self._normalize_ts(row["updated_at"]),
                }
                for field in _HOST_FIELDS:
                    value = row[field]
                    if field in _BOOL_FIELDS and value is not None:
                        value = bool(value)
                    record[field] = value
                payload["hosts"].append(record)

            link_rows = conn.execute(
                """SELECT ht.sync_uuid, ht.updated_at,
                          h.sync_uuid AS host_sync_uuid,
                          t.sync_uuid AS tag_sync_uuid
                   FROM host_tags ht
                   JOIN hosts h ON h.id = ht.host_id
                   JOIN tags t ON t.id = ht.tag_id
                   WHERE ht.sync_uuid IS NOT NULL"""
            ).fetchall()
            for row in link_rows:
                payload["host_tags"].append(
                    {
                        "sync_uuid": row["sync_uuid"],
                        "host_sync_uuid": row["host_sync_uuid"],
                        "tag_sync_uuid": row["tag_sync_uuid"],
                        "updated_at": self._normalize_ts(row["updated_at"]),
                    }
                )

            tomb_rows = conn.execute(
                "SELECT entity_type, sync_uuid, deleted_at FROM sync_tombstones"
            ).fetchall()
            for row in tomb_rows:
                payload["tombstones"].append(
                    {
                        "entity_type": row["entity_type"],
                        "sync_uuid": row["sync_uuid"],
                        "deleted_at": self._normalize_ts(row["deleted_at"]),
                    }
                )

        return payload

    async def _download_remote_records(self) -> dict[str, Any]:
        tmp = self._data_dir / ".sync_records_remote.json"
        try:
            await self._provider.download_file(
                f"{self._cloud_folder}/{_SYNC_RECORDS_FILE}",
                str(tmp),
            )
            return json.loads(tmp.read_text(encoding="utf-8"))
        except Exception:
            return self._empty_payload()
        finally:
            if tmp.exists():
                tmp.unlink()

    async def _upload_remote_records(self, payload: dict[str, Any]) -> None:
        tmp = self._data_dir / ".sync_records_upload.json"
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        try:
            await self._provider.upload_file(
                str(tmp),
                f"{self._cloud_folder}/{_SYNC_RECORDS_FILE}",
            )
        finally:
            if tmp.exists():
                tmp.unlink()

    def _prune_local_tombstones(self) -> None:
        """Delete tombstones older than the retention window."""
        cutoff = (
            datetime.now(tz=timezone.utc)
            - timedelta(days=_TOMBSTONE_RETENTION_DAYS)
        ).isoformat(timespec="seconds").replace("+00:00", "Z")
        with self._db.connection() as conn:
            deleted = conn.execute(
                "DELETE FROM sync_tombstones WHERE deleted_at < ?", (cutoff,)
            ).rowcount
            conn.commit()
        if deleted:
            logger.info("Pruned %d expired tombstone(s)", deleted)

    def _merge_payloads(
        self, local: dict[str, Any], remote: dict[str, Any]
    ) -> dict[str, Any]:
        """LWW merge of local and remote payloads, applying tombstones."""
        merged = self._empty_payload()

        # Collect all tombstones from both sides
        all_tombs: dict[tuple[str, str], str] = {}
        for t in local.get("tombstones", []) + remote.get("tombstones", []):
            key = (t["entity_type"], t["sync_uuid"])
            existing = all_tombs.get(key, "")
            if t["deleted_at"] > existing:
                all_tombs[key] = t["deleted_at"]
        merged["tombstones"] = sorted(
            [
                {"entity_type": k[0], "sync_uuid": k[1], "deleted_at": v}
                for k, v in all_tombs.items()
            ],
            key=lambda r: (r["entity_type"], r["sync_uuid"]),
        )

        tomb_set = {(t["entity_type"], t["sync_uuid"]) for t in merged["tombstones"]}

        # Merge each entity type with LWW
        for entity in ("groups", "tags", "hosts", "host_tags"):
            local_map: dict[str, dict[str, Any]] = {
                r["sync_uuid"]: r for r in local.get(entity, [])
            }
            remote_map: dict[str, dict[str, Any]] = {
                r["sync_uuid"]: r for r in remote.get(entity, [])
            }
            all_uuids = set(local_map.keys()) | set(remote_map.keys())
            result: list[dict[str, Any]] = []

            for uuid in all_uuids:
                # Skip records that have been tombstoned
                if (entity, uuid) in tomb_set:
                    continue

                l_rec = local_map.get(uuid)
                r_rec = remote_map.get(uuid)

                if l_rec and not r_rec:
                    result.append(l_rec)
                elif r_rec and not l_rec:
                    result.append(r_rec)
                else:
                    # Both exist — LWW: newer updated_at wins
                    l_ts = self._parse_ts(l_rec["updated_at"])
                    r_ts = self._parse_ts(r_rec["updated_at"])
                    result.append(r_rec if r_ts > l_ts else l_rec)

            merged[entity] = sorted(result, key=lambda r: r["sync_uuid"])

        return merged

    def _apply_merged_payload(self, payload: dict[str, Any]) -> dict[str, int]:
        """Write merged records into the local database. Returns stats."""
        stats = {"added": 0, "updated": 0, "deleted": 0, "pushed": 0}
        with self._db.connection() as conn:
            # --- Groups ---
            # Build sync_uuid -> local id map
            local_groups = {
                r["sync_uuid"]: r["id"]
                for r in conn.execute(
                    "SELECT id, sync_uuid FROM groups_ WHERE sync_uuid IS NOT NULL"
                ).fetchall()
            }
            remote_group_uuids = {g["sync_uuid"] for g in payload.get("groups", [])}

            for g in payload.get("groups", []):
                if g["sync_uuid"] in local_groups:
                    conn.execute(
                        """UPDATE groups_ SET name=?, icon=?, color=?,
                           default_identity_id=?, default_jump_host_id=?,
                           sort_order=?, updated_at=?
                           WHERE sync_uuid=?""",
                        (
                            g["name"], g["icon"], g["color"],
                            g.get("default_identity_id"),
                            g.get("default_jump_host_id"),
                            g.get("sort_order", 0), g["updated_at"],
                            g["sync_uuid"],
                        ),
                    )
                    stats["updated"] += 1
                else:
                    conn.execute(
                        """INSERT INTO groups_
                           (sync_uuid, vault_id, name, icon, color,
                            default_identity_id, default_jump_host_id,
                            sort_order, updated_at)
                           VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            g["sync_uuid"], g["name"], g["icon"], g["color"],
                            g.get("default_identity_id"),
                            g.get("default_jump_host_id"),
                            g.get("sort_order", 0), g["updated_at"],
                        ),
                    )
                    stats["added"] += 1

            # Resolve parent_id after all groups exist
            for g in payload.get("groups", []):
                parent_uuid = g.get("parent_sync_uuid")
                if parent_uuid:
                    row = conn.execute(
                        "SELECT id FROM groups_ WHERE sync_uuid=?", (parent_uuid,)
                    ).fetchone()
                    if row:
                        conn.execute(
                            "UPDATE groups_ SET parent_id=? WHERE sync_uuid=?",
                            (row["id"], g["sync_uuid"]),
                        )

            # Delete local groups that were tombstoned
            tomb_group_uuids = {
                t["sync_uuid"]
                for t in payload.get("tombstones", [])
                if t["entity_type"] == "groups"
            }
            for uuid in tomb_group_uuids:
                if uuid in local_groups:
                    conn.execute("DELETE FROM groups_ WHERE sync_uuid=?", (uuid,))
                    stats["deleted"] += 1

            # --- Tags ---
            local_tags = {
                r["sync_uuid"]: r["id"]
                for r in conn.execute(
                    "SELECT id, sync_uuid FROM tags WHERE sync_uuid IS NOT NULL"
                ).fetchall()
            }

            for t in payload.get("tags", []):
                if t["sync_uuid"] in local_tags:
                    conn.execute(
                        "UPDATE tags SET name=?, color=?, updated_at=? WHERE sync_uuid=?",
                        (t["name"], t["color"], t["updated_at"], t["sync_uuid"]),
                    )
                    stats["updated"] += 1
                else:
                    conn.execute(
                        "INSERT INTO tags (sync_uuid, name, color, updated_at) VALUES (?, ?, ?, ?)",
                        (t["sync_uuid"], t["name"], t["color"], t["updated_at"]),
                    )
                    stats["added"] += 1

            tomb_tag_uuids = {
                t["sync_uuid"]
                for t in payload.get("tombstones", [])
                if t["entity_type"] == "tags"
            }
            for uuid in tomb_tag_uuids:
                if uuid in local_tags:
                    conn.execute("DELETE FROM tags WHERE sync_uuid=?", (uuid,))
                    stats["deleted"] += 1

            # --- Hosts ---
            local_hosts = {
                r["sync_uuid"]: r["id"]
                for r in conn.execute(
                    "SELECT id, sync_uuid FROM hosts WHERE sync_uuid IS NOT NULL"
                ).fetchall()
            }

            for h in payload.get("hosts", []):
                # Resolve group_id from sync_uuid
                group_id = None
                gsuid = h.get("group_sync_uuid")
                if gsuid:
                    row = conn.execute(
                        "SELECT id FROM groups_ WHERE sync_uuid=?", (gsuid,)
                    ).fetchone()
                    if row:
                        group_id = row["id"]

                # Resolve ssh_host_chain_id
                chain_id = None
                csuid = h.get("ssh_host_chain_sync_uuid")
                if csuid:
                    row = conn.execute(
                        "SELECT id FROM hosts WHERE sync_uuid=?", (csuid,)
                    ).fetchone()
                    if row:
                        chain_id = row["id"]

                field_values = {f: h.get(f) for f in _HOST_FIELDS}
                field_values["group_id"] = group_id
                field_values["ssh_host_chain_id"] = chain_id

                if h["sync_uuid"] in local_hosts:
                    set_clause = ", ".join(f"{f}=?" for f in field_values)
                    conn.execute(
                        f"UPDATE hosts SET {set_clause}, updated_at=? WHERE sync_uuid=?",
                        (*field_values.values(), h["updated_at"], h["sync_uuid"]),
                    )
                    stats["updated"] += 1
                else:
                    cols = ["sync_uuid"] + list(field_values.keys()) + ["updated_at"]
                    placeholders = ", ".join("?" for _ in cols)
                    conn.execute(
                        f"INSERT INTO hosts ({', '.join(cols)}) VALUES ({placeholders})",
                        (h["sync_uuid"], *field_values.values(), h["updated_at"]),
                    )
                    stats["added"] += 1

            tomb_host_uuids = {
                t["sync_uuid"]
                for t in payload.get("tombstones", [])
                if t["entity_type"] == "hosts"
            }
            for uuid in tomb_host_uuids:
                if uuid in local_hosts:
                    conn.execute("DELETE FROM hosts WHERE sync_uuid=?", (uuid,))
                    stats["deleted"] += 1

            # --- Host Tags ---
            local_ht = {
                r["sync_uuid"]: (r["host_id"], r["tag_id"])
                for r in conn.execute(
                    "SELECT sync_uuid, host_id, tag_id FROM host_tags WHERE sync_uuid IS NOT NULL"
                ).fetchall()
            }

            for ht in payload.get("host_tags", []):
                host_row = conn.execute(
                    "SELECT id FROM hosts WHERE sync_uuid=?",
                    (ht.get("host_sync_uuid"),),
                ).fetchone()
                tag_row = conn.execute(
                    "SELECT id FROM tags WHERE sync_uuid=?",
                    (ht.get("tag_sync_uuid"),),
                ).fetchone()
                if not host_row or not tag_row:
                    continue

                host_id = host_row["id"]
                tag_id = tag_row["id"]

                if ht["sync_uuid"] in local_ht:
                    conn.execute(
                        "UPDATE host_tags SET host_id=?, tag_id=?, updated_at=? WHERE sync_uuid=?",
                        (host_id, tag_id, ht["updated_at"], ht["sync_uuid"]),
                    )
                    stats["updated"] += 1
                else:
                    conn.execute(
                        """INSERT OR REPLACE INTO host_tags
                           (host_id, tag_id, sync_uuid, updated_at)
                           VALUES (?, ?, ?, ?)""",
                        (host_id, tag_id, ht["sync_uuid"], ht["updated_at"]),
                    )
                    stats["added"] += 1

            tomb_ht_uuids = {
                t["sync_uuid"]
                for t in payload.get("tombstones", [])
                if t["entity_type"] == "host_tags"
            }
            for uuid in tomb_ht_uuids:
                if uuid in local_ht:
                    conn.execute("DELETE FROM host_tags WHERE sync_uuid=?", (uuid,))
                    stats["deleted"] += 1

            # --- Sync tombstones to local table ---
            for t in payload.get("tombstones", []):
                conn.execute(
                    """INSERT OR REPLACE INTO sync_tombstones
                       (entity_type, sync_uuid, deleted_at) VALUES (?, ?, ?)""",
                    (t["entity_type"], t["sync_uuid"], t["deleted_at"]),
                )

            conn.commit()
        logger.info("Applied merged payload to local DB")
        return stats

    async def _pull_file(self, filename: str) -> None:
        """Download a single sync file from cloud."""
        remote = f"{self._cloud_folder}/{filename}"
        local = str(self._data_dir / filename)
        try:
            info = await self._provider.get_file_info(remote)
            if info:
                await self._provider.download_file(remote, local)
                logger.info("Pulled: %s", filename)
        except Exception:
            logger.warning("Could not pull %s", filename)

    async def _push_file(self, filename: str) -> None:
        """Upload a single sync file to cloud."""
        local_path = self._data_dir / filename
        if local_path.exists():
            await self._provider.upload_file(
                str(local_path), f"{self._cloud_folder}/{filename}"
            )
            logger.info("Pushed: %s", filename)

    async def _get_remote_meta(self) -> dict | None:
        """Download and parse sync_meta.json from cloud."""
        tmp = self._data_dir / ".sync_meta_remote.json"
        try:
            await self._provider.download_file(
                f"{self._cloud_folder}/sync_meta.json", str(tmp)
            )
            data = json.loads(tmp.read_text(encoding="utf-8"))
            return data
        except Exception:
            return None
        finally:
            if tmp.exists():
                tmp.unlink()

    def _backup_local(self) -> None:
        """Create a timestamped backup of the local database."""
        self._backups_dir.mkdir(parents=True, exist_ok=True)
        db = self._data_dir / "rlqshell.db"
        if db.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = self._backups_dir / f"rlqshell_{ts}.db"
            shutil.copy2(db, backup)
            logger.info("Backup created: %s", backup.name)

            # Keep only last 10 backups
            backups = sorted(self._backups_dir.glob("rlqshell_*.db"))
            for old in backups[:-10]:
                old.unlink()

    async def shutdown(self) -> None:
        """Close provider session and stop timers."""
        self.stop_auto_sync()
        if self._provider:
            await self._provider.close()

