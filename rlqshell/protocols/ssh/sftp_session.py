"""SFTP session — async file operations over paramiko."""

from __future__ import annotations

import asyncio
import logging
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath

import paramiko

logger = logging.getLogger(__name__)


@dataclass
class FileEntry:
    """Single remote file/directory entry."""

    name: str
    path: str
    size: int = 0
    is_dir: bool = False
    is_link: bool = False
    permissions: str = ""
    modified: datetime | None = None
    owner: str = ""
    group: str = ""


class SFTPSession:
    """Async wrapper around paramiko.SFTPClient."""

    def __init__(self, transport: paramiko.Transport) -> None:
        self._transport = transport
        self._sftp: paramiko.SFTPClient | None = None
        self._cwd = "/"

    @property
    def cwd(self) -> str:
        return self._cwd

    @property
    def is_open(self) -> bool:
        return self._sftp is not None

    async def open(self) -> None:
        """Open the SFTP channel."""
        loop = asyncio.get_running_loop()
        self._sftp = await loop.run_in_executor(
            None, paramiko.SFTPClient.from_transport, self._transport
        )
        if self._sftp:
            try:
                self._cwd = await loop.run_in_executor(None, self._sftp.normalize, ".")
            except Exception:
                self._cwd = "/"
        logger.info("SFTP session opened, cwd=%s", self._cwd)

    async def close(self) -> None:
        if self._sftp:
            self._sftp.close()
            self._sftp = None

    async def list_dir(self, path: str | None = None) -> list[FileEntry]:
        """List directory contents."""
        if self._sftp is None:
            return []

        target = path or self._cwd
        loop = asyncio.get_running_loop()

        attrs_list: list[paramiko.SFTPAttributes] = await loop.run_in_executor(
            None, self._sftp.listdir_attr, target
        )

        entries: list[FileEntry] = []
        for attr in attrs_list:
            name = attr.filename
            if name in (".", ".."):
                continue

            full_path = str(PurePosixPath(target) / name)
            is_dir = stat.S_ISDIR(attr.st_mode) if attr.st_mode else False
            is_link = stat.S_ISLNK(attr.st_mode) if attr.st_mode else False

            mtime = None
            if attr.st_mtime:
                mtime = datetime.fromtimestamp(attr.st_mtime)

            perms = self._format_permissions(attr.st_mode) if attr.st_mode else ""

            entries.append(FileEntry(
                name=name,
                path=full_path,
                size=attr.st_size or 0,
                is_dir=is_dir,
                is_link=is_link,
                permissions=perms,
                modified=mtime,
                owner=str(attr.st_uid or ""),
                group=str(attr.st_gid or ""),
            ))

        # Sort: directories first, then alphabetical
        entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))
        return entries

    async def cd(self, path: str) -> str:
        """Change current directory. Returns the new cwd."""
        if self._sftp is None:
            return self._cwd

        loop = asyncio.get_running_loop()
        new_path = str(PurePosixPath(self._cwd) / path) if not path.startswith("/") else path
        normalized = await loop.run_in_executor(None, self._sftp.normalize, new_path)
        self._cwd = normalized
        return self._cwd

    async def download(
        self,
        remote_path: str,
        local_path: str,
        progress_callback=None,
    ) -> None:
        """Download a file from the remote server."""
        if self._sftp is None:
            raise RuntimeError("SFTP not connected")

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self._sftp.get, remote_path, local_path,
            progress_callback,
        )
        logger.info("Downloaded %s → %s", remote_path, local_path)

    async def upload(
        self,
        local_path: str,
        remote_path: str,
        progress_callback=None,
    ) -> None:
        """Upload a file to the remote server."""
        if self._sftp is None:
            raise RuntimeError("SFTP not connected")

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self._sftp.put, local_path, remote_path,
            progress_callback,
        )
        logger.info("Uploaded %s → %s", local_path, remote_path)

    async def mkdir(self, path: str) -> None:
        """Create a remote directory."""
        if self._sftp is None:
            raise RuntimeError("SFTP not connected")

        loop = asyncio.get_running_loop()
        full_path = str(PurePosixPath(self._cwd) / path) if not path.startswith("/") else path
        await loop.run_in_executor(None, self._sftp.mkdir, full_path)
        logger.info("Created directory: %s", full_path)

    async def delete(self, path: str) -> None:
        """Delete a remote file."""
        if self._sftp is None:
            raise RuntimeError("SFTP not connected")

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._sftp.remove, path)
        logger.info("Deleted: %s", path)

    async def rmdir(self, path: str) -> None:
        """Delete a remote directory."""
        if self._sftp is None:
            raise RuntimeError("SFTP not connected")

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._sftp.rmdir, path)
        logger.info("Removed directory: %s", path)

    async def rename(self, old_path: str, new_path: str) -> None:
        """Rename a remote file or directory."""
        if self._sftp is None:
            raise RuntimeError("SFTP not connected")

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._sftp.rename, old_path, new_path)
        logger.info("Renamed %s → %s", old_path, new_path)

    async def read_file(self, remote_path: str, max_size: int = 5 * 1024 * 1024) -> bytes:
        """Read a remote file into memory. Raises ValueError if file exceeds max_size."""
        if self._sftp is None:
            raise RuntimeError("SFTP not connected")

        loop = asyncio.get_running_loop()
        attrs = await loop.run_in_executor(None, self._sftp.stat, remote_path)
        if attrs.st_size and attrs.st_size > max_size:
            raise ValueError(
                f"File too large ({attrs.st_size} bytes, max {max_size})"
            )

        def _read():
            with self._sftp.open(remote_path, "rb") as f:
                return f.read()

        return await loop.run_in_executor(None, _read)

    async def write_file(self, remote_path: str, data: bytes) -> None:
        """Write data to a remote file."""
        if self._sftp is None:
            raise RuntimeError("SFTP not connected")

        loop = asyncio.get_running_loop()

        def _write():
            with self._sftp.open(remote_path, "wb") as f:
                f.write(data)

        await loop.run_in_executor(None, _write)
        logger.info("Written %d bytes to %s", len(data), remote_path)

    async def stat(self, path: str) -> paramiko.SFTPAttributes | None:
        """Get file attributes."""
        if self._sftp is None:
            return None

        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self._sftp.stat, path)
        except FileNotFoundError:
            return None

    @staticmethod
    def _format_permissions(mode: int) -> str:
        """Format Unix permissions into rwx string."""
        parts = []
        for shift in (6, 3, 0):
            m = (mode >> shift) & 0o7
            parts.append(
                ("r" if m & 4 else "-")
                + ("w" if m & 2 else "-")
                + ("x" if m & 1 else "-")
            )
        prefix = "d" if stat.S_ISDIR(mode) else "l" if stat.S_ISLNK(mode) else "-"
        return prefix + "".join(parts)
