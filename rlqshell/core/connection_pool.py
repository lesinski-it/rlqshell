"""Connection pool — tracks active connections."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from rlqshell.protocols.base import AbstractConnection

logger = logging.getLogger(__name__)


class ConnectionPool(QObject):
    """Registry of active protocol connections."""

    connection_added = Signal(str)  # connection id
    connection_removed = Signal(str)  # connection id
    connection_count_changed = Signal(int)
    host_status_changed = Signal(int, str)  # host_id, status ("connected"/"disconnected")

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._connections: dict[str, AbstractConnection] = {}
        self._conn_to_host: dict[str, int] = {}  # conn_id → host_id
        self._host_conn_count: dict[int, int] = {}  # host_id → active connection count

    @property
    def count(self) -> int:
        return len(self._connections)

    def add(self, conn_id: str, connection: AbstractConnection, host_id: int | None = None) -> None:
        self._connections[conn_id] = connection
        if host_id is not None:
            self._conn_to_host[conn_id] = host_id
            prev = self._host_conn_count.get(host_id, 0)
            self._host_conn_count[host_id] = prev + 1
            if prev == 0:
                self.host_status_changed.emit(host_id, "connected")
        connection.disconnected.connect(lambda cid=conn_id: self.remove(cid))
        self.connection_added.emit(conn_id)
        self.connection_count_changed.emit(self.count)
        logger.info("Connection added: %s (host=%s, total: %d)", conn_id, host_id, self.count)

    def remove(self, conn_id: str) -> None:
        conn = self._connections.pop(conn_id, None)
        host_id = self._conn_to_host.pop(conn_id, None)
        if host_id is not None:
            cnt = self._host_conn_count.get(host_id, 1) - 1
            if cnt <= 0:
                self._host_conn_count.pop(host_id, None)
                self.host_status_changed.emit(host_id, "disconnected")
            else:
                self._host_conn_count[host_id] = cnt
        if conn is not None:
            self.connection_removed.emit(conn_id)
            self.connection_count_changed.emit(self.count)
            logger.info("Connection removed: %s (host=%s, total: %d)", conn_id, host_id, self.count)

    def get(self, conn_id: str) -> AbstractConnection | None:
        return self._connections.get(conn_id)

    def is_host_connected(self, host_id: int) -> bool:
        """Check if a host has any active connections."""
        return self._host_conn_count.get(host_id, 0) > 0

    def connected_host_ids(self) -> set[int]:
        """Return set of host_ids with active connections."""
        return set(self._host_conn_count.keys())

    def close_all(self) -> None:
        for conn_id in list(self._connections):
            conn = self._connections.get(conn_id)
            if conn:
                conn.close()
        self._connections.clear()
        # Emit disconnected for all tracked hosts
        for host_id in list(self._host_conn_count):
            self.host_status_changed.emit(host_id, "disconnected")
        self._conn_to_host.clear()
        self._host_conn_count.clear()
        self.connection_count_changed.emit(0)
