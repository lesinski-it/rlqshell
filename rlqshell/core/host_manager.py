"""CRUD operations for Hosts, Groups, and Tags."""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4

from rlqshell.core.database import Database
from rlqshell.core.models.host import Group, Host, Tag

logger = logging.getLogger(__name__)


class HostManager:
    """Manages hosts, groups, and tags in the database."""

    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    def _new_sync_uuid() -> str:
        return str(uuid4())

    def _record_tombstone(self, entity_type: str, sync_uuid: str | None) -> None:
        if not sync_uuid:
            return
        deleted_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        self._db.execute(
            "INSERT OR REPLACE INTO sync_tombstones (entity_type, sync_uuid, deleted_at) "
            "VALUES (?, ?, ?)",
            (entity_type, sync_uuid, deleted_at),
        )

    # --- Hosts ---

    def create_host(self, host: Host) -> int:
        """Insert a new host and return its id."""
        sync_uuid = host.sync_uuid or self._new_sync_uuid()
        cursor = self._db.execute(
            """INSERT INTO hosts (
                sync_uuid, vault_id, group_id, label, address, protocol,
                ssh_port, ssh_identity_id, ssh_host_chain_id,
                ssh_startup_snippet_id, ssh_keep_alive,
                ssh_agent_forwarding, ssh_x11_forwarding, ssh_compression,
                rdp_port, rdp_username, rdp_domain, rdp_resolution,
                rdp_color_depth, rdp_audio, rdp_clipboard, rdp_drive_mapping,
                vnc_port, vnc_quality, vnc_view_only, vnc_clipboard,
                telnet_port, telnet_raw_mode,
                serial_port_path, serial_baud_rate, serial_data_bits,
                serial_stop_bits, serial_parity, serial_flow_control,
                terminal_theme, terminal_font, terminal_font_size,
                notes, color_label, sort_order
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?
            )""",
            (
                sync_uuid,
                host.vault_id,
                host.group_id,
                host.label,
                host.address,
                host.protocol,
                host.ssh_port, host.ssh_identity_id, host.ssh_host_chain_id,
                host.ssh_startup_snippet_id, host.ssh_keep_alive,
                host.ssh_agent_forwarding, host.ssh_x11_forwarding, host.ssh_compression,
                host.rdp_port, host.rdp_username, host.rdp_domain, host.rdp_resolution,
                host.rdp_color_depth, host.rdp_audio, host.rdp_clipboard,
                host.rdp_drive_mapping,
                host.vnc_port, host.vnc_quality, host.vnc_view_only,
                host.vnc_clipboard,
                host.telnet_port, host.telnet_raw_mode,
                host.serial_port_path, host.serial_baud_rate, host.serial_data_bits,
                host.serial_stop_bits, host.serial_parity, host.serial_flow_control,
                host.terminal_theme, host.terminal_font, host.terminal_font_size,
                host.notes, host.color_label, host.sort_order,
            ),
        )
        host_id = cursor.lastrowid
        assert host_id is not None
        logger.debug("Created host %d: %s", host_id, host.label)
        return host_id

    def reorder_hosts(self, ordered_ids: list[int]) -> None:
        """Update sort_order for hosts based on their position in the list."""
        for idx, host_id in enumerate(ordered_ids):
            self._db.execute(
                "UPDATE hosts SET sort_order = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (idx, host_id),
            )

    def move_host_to_group(self, host_id: int, group_id: int | None) -> None:
        """Move a host to a different group."""
        self._db.execute(
            "UPDATE hosts SET group_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (group_id, host_id),
        )

    def update_host(self, host: Host) -> None:
        """Update an existing host."""
        self._db.execute(
            """UPDATE hosts SET
                vault_id=?, group_id=?, label=?, address=?, protocol=?,
                ssh_port=?, ssh_identity_id=?, ssh_host_chain_id=?,
                ssh_startup_snippet_id=?, ssh_keep_alive=?,
                ssh_agent_forwarding=?, ssh_x11_forwarding=?, ssh_compression=?,
                rdp_port=?, rdp_username=?, rdp_domain=?, rdp_resolution=?,
                rdp_color_depth=?, rdp_audio=?, rdp_clipboard=?, rdp_drive_mapping=?,
                vnc_port=?, vnc_quality=?, vnc_view_only=?, vnc_clipboard=?,
                telnet_port=?, telnet_raw_mode=?,
                serial_port_path=?, serial_baud_rate=?, serial_data_bits=?,
                serial_stop_bits=?, serial_parity=?, serial_flow_control=?,
                terminal_theme=?, terminal_font=?, terminal_font_size=?,
                notes=?, color_label=?, sort_order=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?""",
            (
                host.vault_id, host.group_id, host.label, host.address, host.protocol,
                host.ssh_port, host.ssh_identity_id, host.ssh_host_chain_id,
                host.ssh_startup_snippet_id, host.ssh_keep_alive,
                host.ssh_agent_forwarding, host.ssh_x11_forwarding, host.ssh_compression,
                host.rdp_port, host.rdp_username, host.rdp_domain, host.rdp_resolution,
                host.rdp_color_depth, host.rdp_audio, host.rdp_clipboard,
                host.rdp_drive_mapping,
                host.vnc_port, host.vnc_quality, host.vnc_view_only,
                host.vnc_clipboard,
                host.telnet_port, host.telnet_raw_mode,
                host.serial_port_path, host.serial_baud_rate, host.serial_data_bits,
                host.serial_stop_bits, host.serial_parity, host.serial_flow_control,
                host.terminal_theme, host.terminal_font, host.terminal_font_size,
                host.notes, host.color_label, host.sort_order,
                host.id,
            ),
        )

    def delete_host(self, host_id: int) -> None:
        """Delete a host by id."""
        row = self._db.fetchone("SELECT sync_uuid FROM hosts WHERE id=?", (host_id,))
        self._record_tombstone("hosts", row["sync_uuid"] if row else None)
        self._db.execute("DELETE FROM hosts WHERE id=?", (host_id,))

    def get_host(self, host_id: int) -> Host | None:
        """Fetch a single host by id."""
        row = self._db.fetchone("SELECT * FROM hosts WHERE id=?", (host_id,))
        if row is None:
            return None
        host = self._row_to_host(row)
        host.tags = self.get_host_tags(host_id)
        return host

    def list_hosts(
        self,
        vault_id: int = 1,
        group_id: int | None = None,
        search: str | None = None,
        protocol: str | None = None,
        tag_ids: list[int] | None = None,
    ) -> list[Host]:
        """List hosts with optional filtering."""
        sql = "SELECT * FROM hosts WHERE vault_id=?"
        params: list = [vault_id]

        if group_id is not None:
            sql += " AND group_id=?"
            params.append(group_id)

        if search:
            sql += " AND (label LIKE ? OR address LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like])

        if protocol:
            sql += " AND protocol=?"
            params.append(protocol)

        if tag_ids:
            placeholders = ",".join("?" for _ in tag_ids)
            sql += (
                f" AND id IN ("
                f"SELECT host_id FROM host_tags WHERE tag_id IN ({placeholders})"
                f" GROUP BY host_id HAVING COUNT(DISTINCT tag_id) = ?"
                f")"
            )
            params.extend(tag_ids)
            params.append(len(tag_ids))

        sql += " ORDER BY sort_order, label"
        rows = self._db.fetchall(sql, tuple(params))
        hosts = [self._row_to_host(r) for r in rows]
        for h in hosts:
            if h.id is not None:
                h.tags = self.get_host_tags(h.id)
        return hosts

    def record_connection(self, host_id: int) -> None:
        """Update last_connected and connect_count for a host."""
        self._db.execute(
            """UPDATE hosts SET
                last_connected=CURRENT_TIMESTAMP,
                connect_count=connect_count+1
            WHERE id=?""",
            (host_id,),
        )

    # --- Groups ---

    def create_group(self, group: Group) -> int:
        """Insert a new group and return its id."""
        sync_uuid = group.sync_uuid or self._new_sync_uuid()
        cursor = self._db.execute(
            """INSERT INTO groups_ (
                sync_uuid, vault_id, parent_id, name, icon, color,
                default_identity_id, default_jump_host_id, sort_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sync_uuid, group.vault_id, group.parent_id, group.name, group.icon,
                group.color, group.default_identity_id, group.default_jump_host_id,
                group.sort_order,
            ),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    def update_group(self, group: Group) -> None:
        """Update an existing group."""
        self._db.execute(
            """UPDATE groups_ SET
                vault_id=?, parent_id=?, name=?, icon=?, color=?,
                default_identity_id=?, default_jump_host_id=?, sort_order=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?""",
            (
                group.vault_id, group.parent_id, group.name, group.icon,
                group.color, group.default_identity_id, group.default_jump_host_id,
                group.sort_order, group.id,
            ),
        )

    def delete_group(self, group_id: int) -> None:
        """Delete a group by id."""
        row = self._db.fetchone("SELECT sync_uuid FROM groups_ WHERE id=?", (group_id,))
        self._record_tombstone("groups", row["sync_uuid"] if row else None)
        self._db.execute("DELETE FROM groups_ WHERE id=?", (group_id,))

    def list_groups(self, vault_id: int = 1) -> list[Group]:
        """List all groups in a vault."""
        rows = self._db.fetchall(
            "SELECT * FROM groups_ WHERE vault_id=? ORDER BY sort_order, name",
            (vault_id,),
        )
        return [self._row_to_group(r) for r in rows]

    # --- Tags ---

    def create_tag(self, tag: Tag) -> int:
        """Insert a new tag and return its id."""
        sync_uuid = tag.sync_uuid or self._new_sync_uuid()
        cursor = self._db.execute(
            "INSERT INTO tags (sync_uuid, name, color) VALUES (?, ?, ?)",
            (sync_uuid, tag.name, tag.color),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    def delete_tag(self, tag_id: int) -> None:
        """Delete a tag by id."""
        row = self._db.fetchone("SELECT sync_uuid FROM tags WHERE id=?", (tag_id,))
        self._record_tombstone("tags", row["sync_uuid"] if row else None)
        self._db.execute("DELETE FROM tags WHERE id=?", (tag_id,))

    def list_tags(self) -> list[Tag]:
        """List all tags."""
        rows = self._db.fetchall("SELECT * FROM tags ORDER BY name")
        return [
            Tag(
                id=r["id"],
                sync_uuid=r["sync_uuid"],
                name=r["name"],
                color=r["color"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def add_tag_to_host(self, host_id: int, tag_id: int) -> None:
        """Associate a tag with a host."""
        existing = self._db.fetchone(
            "SELECT sync_uuid FROM host_tags WHERE host_id=? AND tag_id=?",
            (host_id, tag_id),
        )
        if existing:
            self._db.execute(
                "UPDATE host_tags SET updated_at=CURRENT_TIMESTAMP WHERE host_id=? AND tag_id=?",
                (host_id, tag_id),
            )
            return
        self._db.execute(
            "INSERT INTO host_tags (host_id, tag_id, sync_uuid) VALUES (?, ?, ?)",
            (host_id, tag_id, self._new_sync_uuid()),
        )

    def remove_tag_from_host(self, host_id: int, tag_id: int) -> None:
        """Remove a tag from a host."""
        row = self._db.fetchone(
            "SELECT sync_uuid FROM host_tags WHERE host_id=? AND tag_id=?",
            (host_id, tag_id),
        )
        self._record_tombstone("host_tags", row["sync_uuid"] if row else None)
        self._db.execute(
            "DELETE FROM host_tags WHERE host_id=? AND tag_id=?",
            (host_id, tag_id),
        )

    def get_host_tags(self, host_id: int) -> list[Tag]:
        """Get all tags for a host."""
        rows = self._db.fetchall(
            """SELECT t.* FROM tags t
            JOIN host_tags ht ON ht.tag_id = t.id
            WHERE ht.host_id=?
            ORDER BY t.name""",
            (host_id,),
        )
        return [
            Tag(
                id=r["id"],
                sync_uuid=r["sync_uuid"],
                name=r["name"],
                color=r["color"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    # --- Conversions ---

    @staticmethod
    def _row_to_host(row: dict | object) -> Host:
        """Convert a sqlite3.Row to a Host dataclass."""
        return Host(
            id=row["id"],
            sync_uuid=row["sync_uuid"],
            vault_id=row["vault_id"],
            group_id=row["group_id"],
            label=row["label"],
            address=row["address"],
            protocol=row["protocol"],
            ssh_port=row["ssh_port"],
            ssh_identity_id=row["ssh_identity_id"],
            ssh_host_chain_id=row["ssh_host_chain_id"],
            ssh_startup_snippet_id=row["ssh_startup_snippet_id"],
            ssh_keep_alive=row["ssh_keep_alive"],
            ssh_agent_forwarding=bool(row["ssh_agent_forwarding"]),
            ssh_x11_forwarding=bool(row["ssh_x11_forwarding"]),
            ssh_compression=bool(row["ssh_compression"]),
            rdp_port=row["rdp_port"],
            rdp_username=row["rdp_username"],
            rdp_domain=row["rdp_domain"],
            rdp_resolution=row["rdp_resolution"],
            rdp_color_depth=row["rdp_color_depth"],
            rdp_audio=bool(row["rdp_audio"]),
            rdp_clipboard=bool(row["rdp_clipboard"]),
            rdp_drive_mapping=row["rdp_drive_mapping"],
            vnc_port=row["vnc_port"],
            vnc_quality=row["vnc_quality"],
            vnc_view_only=bool(row["vnc_view_only"]),
            vnc_clipboard=bool(row["vnc_clipboard"]),
            telnet_port=row["telnet_port"],
            telnet_raw_mode=bool(row["telnet_raw_mode"]),
            serial_port_path=row["serial_port_path"],
            serial_baud_rate=row["serial_baud_rate"],
            serial_data_bits=row["serial_data_bits"],
            serial_stop_bits=row["serial_stop_bits"],
            serial_parity=row["serial_parity"],
            serial_flow_control=row["serial_flow_control"],
            terminal_theme=row["terminal_theme"],
            terminal_font=row["terminal_font"],
            terminal_font_size=row["terminal_font_size"],
            notes=row["notes"],
            color_label=row["color_label"],
            last_connected=row["last_connected"],
            connect_count=row["connect_count"],
            sort_order=row["sort_order"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_group(row: dict | object) -> Group:
        """Convert a sqlite3.Row to a Group dataclass."""
        return Group(
            id=row["id"],
            sync_uuid=row["sync_uuid"],
            vault_id=row["vault_id"],
            parent_id=row["parent_id"],
            name=row["name"],
            icon=row["icon"],
            color=row["color"],
            default_identity_id=row["default_identity_id"],
            default_jump_host_id=row["default_jump_host_id"],
            sort_order=row["sort_order"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
