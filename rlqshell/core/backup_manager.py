"""Backup and restore manager for RLQShell user data."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from rlqshell.app.constants import APP_VERSION


class BackupManager:
    """Creates and restores ZIP archives of user data files."""

    _EXTRA_FILES = ["vault.key", "config.json"]
    _META_FILE = "backup_meta.json"

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    def create_backup(self, dest_path: Path) -> Path:
        """Create a ZIP backup archive at dest_path.

        If dest_path is a directory, a timestamped filename is generated.
        Returns the path of the created archive.
        """
        if dest_path.is_dir():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest_path = dest_path / f"rlqshell_backup_{ts}.zip"

        meta = {
            "app": "rlqshell",
            "version": APP_VERSION,
            "created_at": datetime.now().isoformat(),
        }

        with zipfile.ZipFile(dest_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(self._META_FILE, json.dumps(meta, indent=2))

            db_path = self._data_dir / "rlqshell.db"
            if db_path.exists():
                self._backup_db(db_path, zf)

            for fname in self._EXTRA_FILES:
                fpath = self._data_dir / fname
                if fpath.exists():
                    zf.write(fpath, fname)

        return dest_path

    def restore_backup(self, zip_path: Path) -> list[str]:
        """Restore user data from a ZIP archive.

        Returns the list of restored filenames. Raises ValueError if archive is invalid.
        """
        if not self.is_valid_backup(zip_path):
            raise ValueError("Invalid backup file — required files are missing.")

        restored: list[str] = []
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                if name == self._META_FILE:
                    continue
                if name == "rlqshell.db":
                    # Restore through sqlite3.backup() so SQLite manages WAL correctly.
                    # Direct file overwrite would leave the old WAL intact, causing it to
                    # be re-applied to the restored DB on next open.
                    self._restore_db(zf)
                else:
                    zf.extract(name, self._data_dir)
                restored.append(name)

        return restored

    def _restore_db(self, zf: zipfile.ZipFile) -> None:
        """Write the restored database into the target path via sqlite3.backup()."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(zf.read("rlqshell.db"))
        try:
            src = sqlite3.connect(str(tmp_path))
            dst = sqlite3.connect(str(self._data_dir / "rlqshell.db"))
            src.backup(dst)
            src.close()
            dst.close()
        finally:
            tmp_path.unlink(missing_ok=True)

    @staticmethod
    def is_valid_backup(zip_path: Path) -> bool:
        """Return True if zip_path is a valid RLQShell backup archive."""
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                return "rlqshell.db" in names and "backup_meta.json" in names
        except (zipfile.BadZipFile, OSError):
            return False

    @staticmethod
    def _backup_db(db_path: Path, zf: zipfile.ZipFile) -> None:
        """Hot-backup the SQLite database into the zip via sqlite3.backup()."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            src = sqlite3.connect(str(db_path))
            dst = sqlite3.connect(str(tmp_path))
            src.backup(dst)
            src.close()
            dst.close()
            zf.write(tmp_path, "rlqshell.db")
        finally:
            tmp_path.unlink(missing_ok=True)
