"""Connection pool — tracks active connections."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from termplus.protocols.base import AbstractConnection

logger = logging.getLogger(__name__)


class ConnectionPool(QObject):
    """Registry of active protocol connections."""

    connection_added = Signal(str)  # connection id
    connection_removed = Signal(str)  # connection id
    connection_count_changed = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._connections: dict[str, AbstractConnection] = {}

    @property
    def count(self) -> int:
        return len(self._connections)

    def add(self, conn_id: str, connection: AbstractConnection) -> None:
        self._connections[conn_id] = connection
        connection.disconnected.connect(lambda cid=conn_id: self.remove(cid))
        self.connection_added.emit(conn_id)
        self.connection_count_changed.emit(self.count)
        logger.info("Connection added: %s (total: %d)", conn_id, self.count)

    def remove(self, conn_id: str) -> None:
        conn = self._connections.pop(conn_id, None)
        if conn is not None:
            self.connection_removed.emit(conn_id)
            self.connection_count_changed.emit(self.count)
            logger.info("Connection removed: %s (total: %d)", conn_id, self.count)

    def get(self, conn_id: str) -> AbstractConnection | None:
        return self._connections.get(conn_id)

    def close_all(self) -> None:
        for conn_id in list(self._connections):
            conn = self._connections.get(conn_id)
            if conn:
                conn.close()
        self._connections.clear()
        self.connection_count_changed.emit(0)
