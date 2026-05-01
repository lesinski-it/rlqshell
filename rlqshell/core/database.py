"""SQLite database manager with full schema initialization."""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator
from uuid import uuid4

logger = logging.getLogger(__name__)

_TABLES_SQL = """
-- === ORGANIZACJA ===

CREATE TABLE IF NOT EXISTS vaults (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL DEFAULT 'Personal',
    description TEXT,
    is_default BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS groups_ (
    id INTEGER PRIMARY KEY,
    sync_uuid TEXT UNIQUE,
    vault_id INTEGER NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES groups_(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    icon TEXT DEFAULT 'folder',
    color TEXT,
    default_identity_id INTEGER,
    default_jump_host_id INTEGER,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    sync_uuid TEXT UNIQUE,
    name TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL DEFAULT '#6c757d',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- === HOSTS ===

CREATE TABLE IF NOT EXISTS hosts (
    id INTEGER PRIMARY KEY,
    sync_uuid TEXT UNIQUE,
    vault_id INTEGER NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
    group_id INTEGER REFERENCES groups_(id) ON DELETE SET NULL,
    label TEXT NOT NULL,
    address TEXT,
    protocol TEXT NOT NULL DEFAULT 'ssh'
        CHECK(protocol IN ('ssh','rdp','vnc','telnet','serial')),
    ssh_port INTEGER DEFAULT 22,
    ssh_identity_id INTEGER,
    ssh_host_chain_id INTEGER REFERENCES hosts(id),
    ssh_startup_snippet_id INTEGER,
    ssh_keep_alive INTEGER DEFAULT 60,
    ssh_agent_forwarding BOOLEAN DEFAULT 0,
    ssh_x11_forwarding BOOLEAN DEFAULT 0,
    ssh_compression BOOLEAN DEFAULT 0,
    rdp_port INTEGER DEFAULT 3389,
    rdp_username TEXT,
    rdp_domain TEXT,
    rdp_resolution TEXT DEFAULT '1920x1080',
    rdp_color_depth INTEGER DEFAULT 32,
    rdp_audio BOOLEAN DEFAULT 0,
    rdp_clipboard BOOLEAN DEFAULT 1,
    rdp_drive_mapping TEXT,
    rdp_smartcard BOOLEAN DEFAULT 0,
    rdp_drives_enabled BOOLEAN DEFAULT 0,
    rdp_printers BOOLEAN DEFAULT 0,
    rdp_fullscreen BOOLEAN DEFAULT 0,
    rdp_multimon BOOLEAN DEFAULT 0,
    vnc_port INTEGER DEFAULT 5900,
    vnc_quality TEXT DEFAULT 'auto'
        CHECK(vnc_quality IN ('auto','lan','broadband','low')),
    vnc_view_only BOOLEAN DEFAULT 0,
    vnc_clipboard BOOLEAN DEFAULT 1,
    telnet_port INTEGER DEFAULT 23,
    telnet_raw_mode BOOLEAN DEFAULT 0,
    serial_port_path TEXT,
    serial_baud_rate INTEGER DEFAULT 115200,
    serial_data_bits INTEGER DEFAULT 8,
    serial_stop_bits TEXT DEFAULT '1',
    serial_parity TEXT DEFAULT 'none'
        CHECK(serial_parity IN ('none','even','odd','mark','space')),
    serial_flow_control TEXT DEFAULT 'none'
        CHECK(serial_flow_control IN ('none','xonxoff','rtscts','dsrdtr')),
    terminal_theme TEXT,
    terminal_font TEXT,
    terminal_font_size INTEGER,
    notes TEXT,
    color_label TEXT,
    last_connected TIMESTAMP,
    connect_count INTEGER DEFAULT 0,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS host_tags (
    host_id INTEGER REFERENCES hosts(id) ON DELETE CASCADE,
    tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    sync_uuid TEXT UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (host_id, tag_id)
);

-- === IDENTITIES & KEYS ===

CREATE TABLE IF NOT EXISTS ssh_keys (
    id INTEGER PRIMARY KEY,
    vault_id INTEGER NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    key_type TEXT NOT NULL
        CHECK(key_type IN ('rsa','ed25519','ecdsa','rsa-cert','ed25519-cert')),
    encrypted_private_key BLOB,
    public_key TEXT,
    encrypted_passphrase BLOB,
    fingerprint TEXT,
    bits INTEGER,
    sync_uuid TEXT UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS identities (
    id INTEGER PRIMARY KEY,
    vault_id INTEGER NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    username TEXT NOT NULL,
    auth_type TEXT NOT NULL DEFAULT 'password'
        CHECK(auth_type IN ('password','key','key+passphrase','agent')),
    encrypted_password BLOB,
    ssh_key_id INTEGER REFERENCES ssh_keys(id),
    sync_uuid TEXT UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- === SNIPPETS ===

CREATE TABLE IF NOT EXISTS snippet_packages (
    id INTEGER PRIMARY KEY,
    vault_id INTEGER NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    icon TEXT,
    sort_order INTEGER DEFAULT 0,
    sync_uuid TEXT UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS snippets (
    id INTEGER PRIMARY KEY,
    vault_id INTEGER NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
    package_id INTEGER REFERENCES snippet_packages(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    script TEXT NOT NULL,
    description TEXT,
    run_as_sudo BOOLEAN DEFAULT 0,
    color_label TEXT,
    sort_order INTEGER DEFAULT 0,
    sync_uuid TEXT UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS snippet_tags (
    snippet_id INTEGER NOT NULL REFERENCES snippets(id) ON DELETE CASCADE,
    name       TEXT    NOT NULL,
    PRIMARY KEY (snippet_id, name)
);

-- === PORT FORWARDING ===

CREATE TABLE IF NOT EXISTS port_forward_rules (
    id INTEGER PRIMARY KEY,
    vault_id INTEGER NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
    host_id INTEGER NOT NULL REFERENCES hosts(id) ON DELETE CASCADE,
    label TEXT,
    direction TEXT NOT NULL
        CHECK(direction IN ('local','remote','dynamic')),
    bind_address TEXT DEFAULT '127.0.0.1',
    local_port INTEGER NOT NULL,
    remote_host TEXT,
    remote_port INTEGER,
    auto_start BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sync_uuid TEXT UNIQUE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- === KNOWN HOSTS ===

CREATE TABLE IF NOT EXISTS known_hosts (
    id INTEGER PRIMARY KEY,
    hostname TEXT NOT NULL,
    port INTEGER DEFAULT 22,
    key_type TEXT NOT NULL,
    host_key TEXT NOT NULL,
    fingerprint TEXT,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sync_uuid TEXT UNIQUE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- === HISTORY ===

CREATE TABLE IF NOT EXISTS connection_history (
    id INTEGER PRIMARY KEY,
    host_id INTEGER REFERENCES hosts(id) ON DELETE SET NULL,
    host_label TEXT,
    address TEXT,
    protocol TEXT,
    connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    disconnected_at TIMESTAMP,
    duration_seconds INTEGER,
    sync_uuid TEXT UNIQUE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS command_history (
    id INTEGER PRIMARY KEY,
    host_id INTEGER REFERENCES hosts(id) ON DELETE SET NULL,
    command TEXT NOT NULL,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- === SYNC STATE ===

CREATE TABLE IF NOT EXISTS sync_state (
    id INTEGER PRIMARY KEY,
    provider TEXT,
    last_sync TIMESTAMP,
    remote_hash TEXT,
    device_id TEXT,
    device_name TEXT,
    encrypted_tokens BLOB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sync_tombstones (
    entity_type TEXT NOT NULL,
    sync_uuid TEXT NOT NULL,
    deleted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (entity_type, sync_uuid)
);

"""

_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_hosts_vault ON hosts(vault_id);
CREATE INDEX IF NOT EXISTS idx_hosts_group ON hosts(group_id);
CREATE INDEX IF NOT EXISTS idx_hosts_label ON hosts(label);
CREATE INDEX IF NOT EXISTS idx_hosts_address ON hosts(address);
CREATE INDEX IF NOT EXISTS idx_snippets_vault ON snippets(vault_id);
CREATE INDEX IF NOT EXISTS idx_connection_history_date ON connection_history(connected_at);
CREATE INDEX IF NOT EXISTS idx_command_history_cmd ON command_history(command);
CREATE UNIQUE INDEX IF NOT EXISTS idx_groups_sync_uuid ON groups_(sync_uuid);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_sync_uuid ON tags(sync_uuid);
CREATE UNIQUE INDEX IF NOT EXISTS idx_hosts_sync_uuid ON hosts(sync_uuid);
CREATE UNIQUE INDEX IF NOT EXISTS idx_host_tags_sync_uuid ON host_tags(sync_uuid);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ssh_keys_sync_uuid ON ssh_keys(sync_uuid);
CREATE UNIQUE INDEX IF NOT EXISTS idx_identities_sync_uuid ON identities(sync_uuid);
CREATE UNIQUE INDEX IF NOT EXISTS idx_snippet_packages_sync_uuid ON snippet_packages(sync_uuid);
CREATE UNIQUE INDEX IF NOT EXISTS idx_snippets_sync_uuid ON snippets(sync_uuid);
CREATE INDEX IF NOT EXISTS idx_tombstones_deleted_at ON sync_tombstones(deleted_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_port_forward_rules_sync_uuid ON port_forward_rules(sync_uuid);
CREATE UNIQUE INDEX IF NOT EXISTS idx_known_hosts_sync_uuid ON known_hosts(sync_uuid);
CREATE UNIQUE INDEX IF NOT EXISTS idx_connection_history_sync_uuid ON connection_history(sync_uuid);
CREATE UNIQUE INDEX IF NOT EXISTS idx_known_hosts_host_port ON known_hosts(hostname, port);
"""


class Database:
    """SQLite database access layer.

    Thread-safe via a lock on write operations. Uses WAL mode for
    concurrent read performance.
    """

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = str(db_path)
        self._lock = threading.Lock()
        self._connection: sqlite3.Connection | None = None

    def initialize(self) -> None:
        """Create all tables and seed default data."""
        conn = self._get_connection()
        conn.executescript(_TABLES_SQL)

        # Seed default vault if not exists
        row = conn.execute("SELECT id FROM vaults WHERE is_default = 1").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO vaults (name, is_default) VALUES ('Personal', 1)"
            )
            conn.commit()

        self._run_migrations(conn)
        conn.executescript(_INDEXES_SQL)

        logger.info("Database initialized: %s", self._db_path)

    @staticmethod
    def _run_migrations(conn: sqlite3.Connection) -> None:
        """Apply schema migrations for existing databases."""
        # Add color_label to snippets (added in v0.2)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(snippets)").fetchall()}
        if "color_label" not in cols:
            conn.execute("ALTER TABLE snippets ADD COLUMN color_label TEXT")
            conn.commit()

        # Separate snippet tags from host tags (v0.3):
        # Old schema: snippet_tags(snippet_id, tag_id) pointing into shared `tags`
        # New schema: snippet_tags(snippet_id, name) — fully denormalised, no
        # overlap with host tags. Orphaned rows in `tags` (i.e. tags that
        # existed only because a snippet referenced them) are purged so
        # HostManager.list_tags() stops seeing them.
        snippet_tags_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(snippet_tags)").fetchall()
        }
        if "tag_id" in snippet_tags_cols:
            logger.info("Migrating snippet_tags to name-based schema")
            # Switch to manual transaction mode so we can interleave PRAGMA
            # (which must run outside a transaction) with explicit BEGIN/COMMIT.
            prev_isolation = conn.isolation_level
            conn.isolation_level = None
            try:
                conn.execute("PRAGMA foreign_keys = OFF")
                conn.execute("BEGIN")

                # Tag ids referenced by snippets but not by any host — these
                # leaked into HostManager.list_tags() and must be removed.
                orphan_ids = [
                    r[0]
                    for r in conn.execute(
                        "SELECT DISTINCT tag_id FROM snippet_tags "
                        "WHERE tag_id NOT IN (SELECT tag_id FROM host_tags)"
                    ).fetchall()
                ]

                conn.execute(
                    """CREATE TABLE snippet_tags_new (
                        snippet_id INTEGER NOT NULL
                            REFERENCES snippets(id) ON DELETE CASCADE,
                        name       TEXT    NOT NULL,
                        PRIMARY KEY (snippet_id, name)
                    )"""
                )
                conn.execute(
                    "INSERT OR IGNORE INTO snippet_tags_new (snippet_id, name) "
                    "SELECT st.snippet_id, t.name "
                    "FROM snippet_tags st JOIN tags t ON t.id = st.tag_id"
                )
                conn.execute("DROP TABLE snippet_tags")
                conn.execute("ALTER TABLE snippet_tags_new RENAME TO snippet_tags")

                if orphan_ids:
                    placeholders = ",".join("?" * len(orphan_ids))
                    conn.execute(
                        f"DELETE FROM tags WHERE id IN ({placeholders})",
                        orphan_ids,
                    )

                conn.execute("COMMIT")
                logger.info(
                    "snippet_tags migrated; removed %d orphaned tag(s)",
                    len(orphan_ids),
                )
            except Exception:
                conn.execute("ROLLBACK")
                raise
            finally:
                conn.execute("PRAGMA foreign_keys = ON")
                conn.isolation_level = prev_isolation

        # Sync v2 metadata for record-level cloud sync.
        def _table_cols(table: str) -> set[str]:
            return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}

        def _add_column_if_missing(table: str, col_name: str, col_ddl: str) -> None:
            if col_name not in _table_cols(table):
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_ddl}")

        _add_column_if_missing("groups_", "sync_uuid", "sync_uuid TEXT")
        _add_column_if_missing("groups_", "updated_at", "updated_at TIMESTAMP")
        _add_column_if_missing("tags", "sync_uuid", "sync_uuid TEXT")
        _add_column_if_missing("tags", "created_at", "created_at TIMESTAMP")
        _add_column_if_missing("tags", "updated_at", "updated_at TIMESTAMP")
        _add_column_if_missing("hosts", "sync_uuid", "sync_uuid TEXT")
        _add_column_if_missing("hosts", "vnc_clipboard", "vnc_clipboard BOOLEAN DEFAULT 1")
        _add_column_if_missing("hosts", "rdp_smartcard", "rdp_smartcard BOOLEAN DEFAULT 0")
        _add_column_if_missing(
            "hosts", "rdp_drives_enabled", "rdp_drives_enabled BOOLEAN DEFAULT 0",
        )
        _add_column_if_missing("hosts", "rdp_printers", "rdp_printers BOOLEAN DEFAULT 0")
        _add_column_if_missing("hosts", "rdp_fullscreen", "rdp_fullscreen BOOLEAN DEFAULT 0")
        _add_column_if_missing("hosts", "rdp_multimon", "rdp_multimon BOOLEAN DEFAULT 0")
        _add_column_if_missing("host_tags", "sync_uuid", "sync_uuid TEXT")
        _add_column_if_missing("host_tags", "created_at", "created_at TIMESTAMP")
        _add_column_if_missing("host_tags", "updated_at", "updated_at TIMESTAMP")

        # SSH keys, identities, snippets sync support
        _add_column_if_missing("ssh_keys", "sync_uuid", "sync_uuid TEXT")
        _add_column_if_missing("ssh_keys", "updated_at", "updated_at TIMESTAMP")
        _add_column_if_missing("identities", "sync_uuid", "sync_uuid TEXT")
        _add_column_if_missing("identities", "updated_at", "updated_at TIMESTAMP")
        _add_column_if_missing("snippet_packages", "sync_uuid", "sync_uuid TEXT")
        _add_column_if_missing("snippet_packages", "created_at", "created_at TIMESTAMP")
        _add_column_if_missing("snippet_packages", "updated_at", "updated_at TIMESTAMP")
        _add_column_if_missing("snippets", "sync_uuid", "sync_uuid TEXT")
        _add_column_if_missing("snippets", "updated_at", "updated_at TIMESTAMP")

        # Auxiliary sync (port_forward_rules, known_hosts, connection_history)
        _add_column_if_missing("port_forward_rules", "sync_uuid", "sync_uuid TEXT")
        _add_column_if_missing("port_forward_rules", "updated_at", "updated_at TIMESTAMP")
        _add_column_if_missing("known_hosts", "sync_uuid", "sync_uuid TEXT")
        _add_column_if_missing("known_hosts", "updated_at", "updated_at TIMESTAMP")
        _add_column_if_missing("connection_history", "sync_uuid", "sync_uuid TEXT")
        _add_column_if_missing("connection_history", "updated_at", "updated_at TIMESTAMP")

        conn.execute(
            "UPDATE groups_ "
            "SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "UPDATE tags "
            "SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP), "
            "updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "UPDATE host_tags "
            "SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP), "
            "updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "UPDATE ssh_keys "
            "SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "UPDATE identities "
            "SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "UPDATE snippet_packages "
            "SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP), "
            "updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "UPDATE snippets "
            "SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "UPDATE port_forward_rules "
            "SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "UPDATE known_hosts "
            "SET updated_at = COALESCE(updated_at, last_seen, first_seen, CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "UPDATE connection_history "
            "SET updated_at = COALESCE(updated_at, connected_at, CURRENT_TIMESTAMP)"
        )

        for row in conn.execute(
            "SELECT id FROM groups_ WHERE sync_uuid IS NULL OR sync_uuid = ''"
        ).fetchall():
            conn.execute(
                "UPDATE groups_ SET sync_uuid=? WHERE id=?",
                (str(uuid4()), row[0]),
            )

        for row in conn.execute(
            "SELECT id FROM tags WHERE sync_uuid IS NULL OR sync_uuid = ''"
        ).fetchall():
            conn.execute(
                "UPDATE tags SET sync_uuid=? WHERE id=?",
                (str(uuid4()), row[0]),
            )

        for row in conn.execute(
            "SELECT id FROM hosts WHERE sync_uuid IS NULL OR sync_uuid = ''"
        ).fetchall():
            conn.execute(
                "UPDATE hosts SET sync_uuid=? WHERE id=?",
                (str(uuid4()), row[0]),
            )

        for row in conn.execute(
            "SELECT host_id, tag_id FROM host_tags "
            "WHERE sync_uuid IS NULL OR sync_uuid = ''"
        ).fetchall():
            conn.execute(
                "UPDATE host_tags SET sync_uuid=? WHERE host_id=? AND tag_id=?",
                (str(uuid4()), row[0], row[1]),
            )

        for table in ("ssh_keys", "identities", "snippet_packages", "snippets"):
            for row in conn.execute(
                f"SELECT id FROM {table} WHERE sync_uuid IS NULL OR sync_uuid = ''"
            ).fetchall():
                conn.execute(
                    f"UPDATE {table} SET sync_uuid=? WHERE id=?",
                    (str(uuid4()), row[0]),
                )

        for table in ("port_forward_rules", "known_hosts", "connection_history"):
            for row in conn.execute(
                f"SELECT id FROM {table} WHERE sync_uuid IS NULL OR sync_uuid = ''"
            ).fetchall():
                conn.execute(
                    f"UPDATE {table} SET sync_uuid=? WHERE id=?",
                    (str(uuid4()), row[0]),
                )

        conn.execute(
            """CREATE TABLE IF NOT EXISTS sync_tombstones (
                entity_type TEXT NOT NULL,
                sync_uuid TEXT NOT NULL,
                deleted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (entity_type, sync_uuid)
            )"""
        )

        conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(
                self._db_path, check_same_thread=False
            )
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA foreign_keys = ON")
        return self._connection

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager that yields a connection (thread-safe for writes)."""
        with self._lock:
            yield self._get_connection()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """Execute a write query (INSERT/UPDATE/DELETE) with locking."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        """Execute a read query and return one row."""
        conn = self._get_connection()
        return conn.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        """Execute a read query and return all rows."""
        conn = self._get_connection()
        return conn.execute(sql, params).fetchall()

    def close(self) -> None:
        """Close the database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
