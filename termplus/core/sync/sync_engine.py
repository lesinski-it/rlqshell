"""Sync engine — orchestrates pull/merge/push to cloud storage."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from termplus.app.constants import APP_VERSION
from termplus.core.sync.conflict_resolver import ConflictResolver
from termplus.core.sync.providers.base import AbstractCloudProvider
from termplus.core.sync.sync_state import SyncState

logger = logging.getLogger(__name__)

_CLOUD_FOLDER = "/Termplus"
_SYNC_FILES = ["termplus.db", "vault.key", "config.json"]


class SyncEngine(QObject):
    """Orchestrates sync: pull → merge → push."""

    sync_started = Signal()
    sync_completed = Signal()
    sync_error = Signal(str)
    sync_conflict = Signal(str, str)  # local_info, remote_info

    def __init__(
        self,
        data_dir: Path,
        sync_state: SyncState,
        conflict_resolver: ConflictResolver | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._data_dir = data_dir
        self._backups_dir = data_dir / "backups"
        self._state = sync_state
        self._resolver = conflict_resolver or ConflictResolver()
        self._provider: AbstractCloudProvider | None = None
        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._on_auto_sync)
        self._syncing = False

    @property
    def provider(self) -> AbstractCloudProvider | None:
        return self._provider

    @property
    def is_syncing(self) -> bool:
        return self._syncing

    def set_provider(self, provider: AbstractCloudProvider) -> None:
        self._provider = provider
        self._state.set_provider(provider.provider_name)

    def start_auto_sync(self, interval_minutes: int = 5) -> None:
        """Start periodic automatic sync."""
        self._auto_timer.start(interval_minutes * 60 * 1000)
        logger.info("Auto-sync enabled: every %d minutes", interval_minutes)

    def stop_auto_sync(self) -> None:
        self._auto_timer.stop()

    def _on_auto_sync(self) -> None:
        import asyncio

        asyncio.ensure_future(self.sync())

    async def sync(self) -> None:
        """Execute full sync cycle: pull → compare → merge → push."""
        if self._provider is None or not self._provider.is_authenticated():
            logger.warning("Sync skipped — no provider or not authenticated")
            return

        if self._syncing:
            logger.warning("Sync already in progress")
            return

        self._syncing = True
        self._state.status = "syncing"
        self.sync_started.emit()

        try:
            # Ensure remote folder exists
            await self._provider.create_folder(_CLOUD_FOLDER)

            # Backup local before sync
            self._backup_local()

            # Compare local vs remote
            db_path = self._data_dir / "termplus.db"
            local_hash = SyncState.compute_file_hash(db_path)

            remote_meta = await self._get_remote_meta()
            remote_hash = remote_meta.get("db_hash", "") if remote_meta else ""

            if local_hash == remote_hash:
                logger.info("Sync: already up to date")
                self._state.update_after_sync(local_hash, remote_hash)
                self.sync_completed.emit()
                return

            # Both changed — resolve conflict
            remote_modified = None
            if remote_meta and remote_meta.get("last_modified"):
                try:
                    remote_modified = datetime.fromisoformat(
                        remote_meta["last_modified"]
                    ).timestamp()
                except Exception:
                    pass

            local_modified = db_path.stat().st_mtime if db_path.exists() else None

            if remote_hash and local_hash and remote_hash != local_hash:
                winner = self._resolver.resolve(local_modified, remote_modified)
            elif not remote_hash:
                winner = "local"  # No remote yet
            else:
                winner = "remote"  # No local (or empty)

            if winner == "remote":
                await self._pull_all()
                local_hash = SyncState.compute_file_hash(db_path)
            else:
                await self._push_all()
                remote_hash = local_hash

            # Update sync meta in cloud
            meta = self._state.build_meta(APP_VERSION, local_hash)
            meta_json = json.dumps(asdict(meta), indent=2)
            meta_path = self._data_dir / "sync_meta.json"
            meta_path.write_text(meta_json, encoding="utf-8")
            await self._provider.upload_file(
                str(meta_path), f"{_CLOUD_FOLDER}/sync_meta.json"
            )

            self._state.update_after_sync(local_hash, local_hash)
            logger.info("Sync completed successfully")
            self.sync_completed.emit()

        except Exception as exc:
            logger.exception("Sync failed")
            self._state.status = "error"
            self.sync_error.emit(str(exc))
        finally:
            self._syncing = False

    async def _pull_all(self) -> None:
        """Download all sync files from cloud."""
        for filename in _SYNC_FILES:
            remote = f"{_CLOUD_FOLDER}/{filename}"
            local = str(self._data_dir / filename)
            try:
                info = await self._provider.get_file_info(remote)
                if info:
                    await self._provider.download_file(remote, local)
            except Exception:
                logger.warning("Could not pull %s", filename)

    async def _push_all(self) -> None:
        """Upload all sync files to cloud."""
        for filename in _SYNC_FILES:
            local_path = self._data_dir / filename
            if local_path.exists():
                await self._provider.upload_file(
                    str(local_path), f"{_CLOUD_FOLDER}/{filename}"
                )

    async def _get_remote_meta(self) -> dict | None:
        """Download and parse sync_meta.json from cloud."""
        tmp = self._data_dir / ".sync_meta_remote.json"
        try:
            await self._provider.download_file(
                f"{_CLOUD_FOLDER}/sync_meta.json", str(tmp)
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
        db = self._data_dir / "termplus.db"
        if db.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = self._backups_dir / f"termplus_{ts}.db"
            shutil.copy2(db, backup)
            logger.info("Backup created: %s", backup.name)

            # Keep only last 10 backups
            backups = sorted(self._backups_dir.glob("termplus_*.db"))
            for old in backups[:-10]:
                old.unlink()
