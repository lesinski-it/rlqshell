"""SQLite database manager with full schema initialization."""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger(__name__)

_SCHEMA_SQL = """
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
    vault_id INTEGER NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES groups_(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    icon TEXT DEFAULT 'folder',
    color TEXT,
    default_identity_id INTEGER,
    default_jump_host_id INTEGER,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL DEFAULT '#6c757d'
);

-- === HOSTS ===

CREATE TABLE IF NOT EXISTS hosts (
    id INTEGER PRIMARY KEY,
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
    vnc_port INTEGER DEFAULT 5900,
    vnc_quality TEXT DEFAULT 'auto'
        CHECK(vnc_quality IN ('auto','lan','broadband','low')),
    vnc_view_only BOOLEAN DEFAULT 0,
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- === SNIPPETS ===

CREATE TABLE IF NOT EXISTS snippet_packages (
    id INTEGER PRIMARY KEY,
    vault_id INTEGER NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    icon TEXT,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS snippets (
    id INTEGER PRIMARY KEY,
    vault_id INTEGER NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
    package_id INTEGER REFERENCES snippet_packages(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    script TEXT NOT NULL,
    description TEXT,
    run_as_sudo BOOLEAN DEFAULT 0,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    duration_seconds INTEGER
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

-- === INDEXES ===

CREATE INDEX IF NOT EXISTS idx_hosts_vault ON hosts(vault_id);
CREATE INDEX IF NOT EXISTS idx_hosts_group ON hosts(group_id);
CREATE INDEX IF NOT EXISTS idx_hosts_label ON hosts(label);
CREATE INDEX IF NOT EXISTS idx_hosts_address ON hosts(address);
CREATE INDEX IF NOT EXISTS idx_snippets_vault ON snippets(vault_id);
CREATE INDEX IF NOT EXISTS idx_connection_history_date ON connection_history(connected_at);
CREATE INDEX IF NOT EXISTS idx_command_history_cmd ON command_history(command);
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
        conn.executescript(_SCHEMA_SQL)

        # Seed default vault if not exists
        row = conn.execute("SELECT id FROM vaults WHERE is_default = 1").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO vaults (name, is_default) VALUES ('Personal', 1)"
            )
            conn.commit()

        logger.info("Database initialized: %s", self._db_path)

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
