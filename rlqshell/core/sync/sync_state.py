"""Sync state — tracks last sync timestamp, hash, and status."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class SyncMeta:
    """Metadata stored alongside synced files in the cloud."""

    last_modified: str = ""
    device_id: str = ""
    device_name: str = ""
    app_version: str = ""
    db_hash: str = ""


class SyncState:
    """Tracks local sync state."""

    def __init__(self, state_path: Path) -> None:
        self._path = state_path
        self._provider: str = ""
        self._last_sync: datetime | None = None
        self._remote_hash: str = ""
        self._local_hash: str = ""
        self._device_id: str = ""
        self._status: str = "idle"  # idle | syncing | error
        self._load()

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def last_sync(self) -> datetime | None:
        return self._last_sync

    @property
    def status(self) -> str:
        return self._status

    @status.setter
    def status(self, value: str) -> None:
        self._status = value

    @property
    def device_id(self) -> str:
        return self._device_id

    def set_provider(self, name: str) -> None:
        self._provider = name
        self._save()

    def update_after_sync(self, local_hash: str, remote_hash: str) -> None:
        self._last_sync = datetime.now()
        self._local_hash = local_hash
        self._remote_hash = remote_hash
        self._status = "idle"
        self._save()

    def needs_sync(self, current_db_path: Path) -> bool:
        """Check if local DB has changed since last sync."""
        current_hash = self.compute_file_hash(current_db_path)
        return current_hash != self._local_hash

    @staticmethod
    def compute_file_hash(file_path: Path) -> str:
        """SHA256 hash of a file."""
        if not file_path.exists():
            return ""
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha.update(chunk)
        return sha.hexdigest()

    def build_meta(self, app_version: str, db_hash: str) -> SyncMeta:
        import platform

        return SyncMeta(
            last_modified=datetime.now().isoformat(),
            device_id=self._device_id,
            device_name=platform.node(),
            app_version=app_version,
            db_hash=db_hash,
        )

    def _load(self) -> None:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._provider = data.get("provider", "")
                self._remote_hash = data.get("remote_hash", "")
                self._local_hash = data.get("local_hash", "")
                self._device_id = data.get("device_id", str(uuid4())[:8])
                last = data.get("last_sync")
                if last:
                    self._last_sync = datetime.fromisoformat(last)
            except Exception:
                logger.warning("Could not load sync state")
        else:
            self._device_id = str(uuid4())[:8]

    def _save(self) -> None:
        data = {
            "provider": self._provider,
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
            "remote_hash": self._remote_hash,
            "local_hash": self._local_hash,
            "device_id": self._device_id,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")
