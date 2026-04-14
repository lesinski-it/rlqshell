"""Port forwarding rule data model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class PortForwardRule:
    """A port forwarding rule tied to a host."""

    id: int | None = None
    vault_id: int = 1
    host_id: int | None = None
    label: str | None = None
    direction: str = "local"  # local | remote | dynamic
    bind_address: str = "127.0.0.1"
    local_port: int = 0
    remote_host: str | None = None
    remote_port: int | None = None
    auto_start: bool = True
    created_at: datetime | None = None
    sync_uuid: str | None = None
    updated_at: datetime | None = None
