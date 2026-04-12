"""Sync engine — orchestrates pull/merge/push to cloud storage."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import aiohttp
from PySide6.QtCore import QObject, QTimer, Signal

from rlqshell.app.constants import APP_VERSION
from rlqshell.core.sync.conflict_resolver import ConflictResolver
from rlqshell.core.sync.providers.base import AbstractCloudProvider
from rlqshell.core.sync.sync_state import SyncState

logger = logging.getLogger(__name__)

_SYNC_FILES = ["rlqshell.db", "vault.key", "config.json"]


class SyncEngine(QObject):
    """Orchestrates sync: pull → merge → push (per-file bidirectional)."""

    sync_started = Signal()
    sync_completed = Signal()
    sync_error = Signal(str)
    sync_conflict = Signal(str, str)  # filename, winner
    sync_skipped = Signal(str)  # reason

    def __init__(
        self,
        data_dir: Path,
        sync_state: SyncState,
        conflict_resolver: ConflictResolver | None = None,
        cloud_folder: str = "/RLQShell",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._data_dir = data_dir
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
        """Execute full sync cycle: per-file bidirectional pull/push."""
        if self._provider is None or not self._provider.is_authenticated():
            logger.warning("Sync skipped — no provider or not authenticated")
            return

        if self._syncing:
            logger.warning("Sync already in progress")
            return

        # Connectivity check
        if not await self._check_connectivity():
            logger.info("Sync skipped — offline")
            self._pending_sync = True
            self.sync_skipped.emit("offline")
            return

        self._syncing = True
        self._pending_sync = False
        self._state.status = "syncing"
        self.sync_started.emit()

        try:
            # Ensure remote folder exists
            await self._provider.create_folder(self._cloud_folder)

            # Backup local before sync
            self._backup_local()

            # Compute local hashes for all sync files
            local_hashes: dict[str, str] = {}
            for filename in _SYNC_FILES:
                path = self._data_dir / filename
                local_hashes[filename] = SyncState.compute_file_hash(path)

            # Get remote metadata
            remote_meta = await self._get_remote_meta()
            remote_hashes: dict[str, str] = {}
            remote_modified_str = None
            if remote_meta:
                remote_modified_str = remote_meta.get("last_modified")
                # Prefer per-file hashes; fall back to single db_hash
                if remote_meta.get("file_hashes"):
                    remote_hashes = remote_meta["file_hashes"]
                elif remote_meta.get("db_hash"):
                    remote_hashes = {"rlqshell.db": remote_meta["db_hash"]}

            # Parse remote modified timestamp for conflict resolution
            remote_modified: float | None = None
            if remote_modified_str:
                try:
                    remote_modified = datetime.fromisoformat(
                        remote_modified_str
                    ).timestamp()
                except Exception:
                    pass

            # Per-file comparison and sync
            any_pushed = False
            any_pulled = False

            for filename in _SYNC_FILES:
                local_hash = local_hashes.get(filename, "")
                remote_hash = remote_hashes.get(filename, "")

                if local_hash == remote_hash:
                    continue  # File unchanged on both sides

                local_path = self._data_dir / filename
                local_modified = (
                    local_path.stat().st_mtime if local_path.exists() else None
                )

                if not remote_hash:
                    # No remote version — push
                    await self._push_file(filename)
                    any_pushed = True
                elif not local_hash:
                    # No local version — pull
                    await self._pull_file(filename)
                    any_pulled = True
                else:
                    # Both changed — resolve conflict
                    winner = self._resolver.resolve(local_modified, remote_modified)
                    self.sync_conflict.emit(filename, winner)
                    if winner == "remote":
                        await self._pull_file(filename)
                        any_pulled = True
                    else:
                        await self._push_file(filename)
                        any_pushed = True

            # Recompute hashes after pulls
            if any_pulled:
                for filename in _SYNC_FILES:
                    path = self._data_dir / filename
                    local_hashes[filename] = SyncState.compute_file_hash(path)

            # Upload updated sync_meta.json
            if any_pushed or any_pulled or not remote_meta:
                db_hash = local_hashes.get("rlqshell.db", "")
                meta = self._state.build_meta(APP_VERSION, db_hash, local_hashes)
                meta_json = json.dumps(asdict(meta), indent=2)
                meta_path = self._data_dir / "sync_meta.json"
                meta_path.write_text(meta_json, encoding="utf-8")
                await self._provider.upload_file(
                    str(meta_path), f"{self._cloud_folder}/sync_meta.json"
                )

            # Persist refreshed tokens if callback set
            if self._token_save_callback and self._provider:
                tokens = self._provider.get_tokens()
                if tokens:
                    self._token_save_callback(tokens[0], tokens[1])

            self._state.update_after_sync(
                local_hashes.get("rlqshell.db", ""),
                local_hashes.get("rlqshell.db", ""),
            )
            logger.info("Sync completed successfully")
            self.sync_completed.emit()

        except Exception as exc:
            logger.exception("Sync failed")
            self._state.status = "error"
            self.sync_error.emit(str(exc))
        finally:
            self._syncing = False

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
