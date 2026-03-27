"""Active connection metadata and history models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ConnectionInfo:
    """Metadata for an active connection (not a DB-persisted model)."""

    host_id: int
    host_label: str
    address: str
    protocol: str
    connected_at: datetime | None = None
    status: str = "disconnected"  # connecting | connected | disconnected | error


@dataclass
class ConnectionHistory:
    """A record of a past connection."""

    id: int | None = None
    host_id: int | None = None
    host_label: str = ""
    address: str = ""
    protocol: str = ""
    connected_at: datetime | None = None
    disconnected_at: datetime | None = None
    duration_seconds: int | None = None


@dataclass
class CommandHistory:
    """A record of an executed command."""

    id: int | None = None
    host_id: int | None = None
    command: str = ""
    executed_at: datetime | None = None
