"""Auto-update manager — checks for new versions and installs updates."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import aiohttp
from PySide6.QtCore import QObject, QTimer, Signal

from rlqshell.app.config import ConfigManager
from rlqshell.app.constants import APP_VERSION

logger = logging.getLogger(__name__)

UPDATE_URL = "https://update.lesinski.it/rlqshell/version.json"


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Parse a version string like '0.2.13' into a comparable tuple."""
    parts: list[int] = []
    for part in version_str.strip().split("."):
        try:
            parts.append(int(part))
        except ValueError:
            break
    return tuple(parts)


class UpdateManager(QObject):
    """Checks for updates, downloads packages and launches the installer."""

    update_available = Signal(dict)
    download_progress = Signal(int, int)  # bytes_downloaded, total_bytes
    download_complete = Signal(str)       # path to verified download
    download_failed = Signal(str)         # error message
    check_failed = Signal(str)

    def __init__(
        self, config: ConfigManager, parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer)
        self._checking = False
        self._downloading = False
        self._latest_manifest: dict | None = None

    # -- lifecycle --

    def start(self) -> None:
        if not self._config.get("updates.auto_check", True):
            return
        interval_m = self._config.get("updates.check_interval_minutes")
        if interval_m is None:
            # migrate legacy hours key
            legacy_h = self._config.get("updates.check_interval_hours", 24)
            interval_m = legacy_h * 60
            self._config.set("updates.check_interval_minutes", interval_m)
            self._config.save()
        self._timer.start(int(interval_m) * 60 * 1000)
        QTimer.singleShot(5000, self._on_timer)
        logger.info("Update checker started (every %d min)", interval_m)

    def stop(self) -> None:
        self._timer.stop()

    # -- check --

    async def check_for_update(self) -> dict | None:
        if self._checking:
            return None
        self._checking = True
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(UPDATE_URL) as resp:
                    if resp.status != 200:
                        raise RuntimeError(f"HTTP {resp.status}")
                    manifest = await resp.json(content_type=None)

            if manifest.get("schema_version") != 1:
                logger.warning("Unknown manifest schema: %s", manifest.get("schema_version"))
                return None

            remote_ver = manifest.get("version", "")
            if not remote_ver:
                return None

            current = _parse_version(APP_VERSION)
            remote = _parse_version(remote_ver)

            forced = manifest.get("forced", False)
            min_ver = manifest.get("minimum_version")
            if min_ver and current < _parse_version(min_ver):
                forced = True

            if remote > current:
                manifest["_forced"] = forced
                self._latest_manifest = manifest
                logger.info("Update available: %s -> %s (forced=%s)", APP_VERSION, remote_ver, forced)
                self.update_available.emit(manifest)
                return manifest

            logger.debug("No update available (current=%s remote=%s)", APP_VERSION, remote_ver)
            return None

        except Exception as exc:
            msg = f"Update check failed: {exc}"
            logger.warning(msg)
            self.check_failed.emit(msg)
            return None
        finally:
            self._checking = False

    # -- download info --

    def get_download_info(self, manifest: dict | None = None) -> dict | None:
        manifest = manifest or self._latest_manifest
        if not manifest:
            return None
        downloads = manifest.get("downloads", {})
        if sys.platform == "win32":
            return downloads.get("msi")
        if sys.platform == "linux":
            return downloads.get("deb")
        return None

    # -- download --

    async def download_update(self, manifest: dict | None = None) -> Path | None:
        if self._downloading:
            return None
        self._downloading = True
        try:
            info = self.get_download_info(manifest)
            if not info:
                self.download_failed.emit("Brak pakietu dla tej platformy.")
                return None

            url = info["url"]
            expected_hash = info["sha256"]
            expected_size = info.get("size_bytes", 0)

            dl_dir = Path(tempfile.mkdtemp(prefix="rlqshell_update_"))

            # check disk space
            free = shutil.disk_usage(dl_dir).free
            if expected_size and free < expected_size * 1.5:
                self.download_failed.emit("Za mało miejsca na dysku.")
                return None

            filename = url.rsplit("/", 1)[-1]
            dest = dl_dir / filename

            logger.info("Downloading update: %s", url)
            timeout = aiohttp.ClientTimeout(total=600)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        self.download_failed.emit(f"Błąd pobierania: HTTP {resp.status}")
                        return None

                    total = int(resp.headers.get("Content-Length", expected_size or 0))
                    downloaded = 0
                    with dest.open("wb") as f:
                        async for chunk in resp.content.iter_chunked(65536):
                            f.write(chunk)
                            downloaded += len(chunk)
                            self.download_progress.emit(downloaded, total)

            # verify hash
            digest = hashlib.sha256()
            with dest.open("rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    digest.update(chunk)
            actual_hash = digest.hexdigest()

            if actual_hash != expected_hash:
                dest.unlink(missing_ok=True)
                msg = "Weryfikacja SHA256 nie powiodła się — pobrany plik może być uszkodzony."
                logger.error(msg)
                self.download_failed.emit(msg)
                return None

            logger.info("Download verified: %s", dest)
            self.download_complete.emit(str(dest))
            return dest

        except Exception as exc:
            msg = f"Pobieranie nie powiodło się: {exc}"
            logger.exception(msg)
            self.download_failed.emit(msg)
            return None
        finally:
            self._downloading = False

    # -- install --

    def launch_installer(self, installer_path: str) -> bool:
        path = Path(installer_path)
        if not path.exists():
            logger.error("Installer not found: %s", path)
            return False

        try:
            if sys.platform == "win32":
                import os

                cmd = ["msiexec", "/i", str(path), "/passive", "/norestart"]
                # Detect per-machine install: if running from Program Files,
                # pass ALLUSERS=1 so MajorUpgrade finds the existing product
                # in HKLM and upgrades in-place instead of installing alongside.
                exe_dir = str(Path(sys.executable).resolve()).lower()
                pf = os.environ.get("ProgramFiles", r"C:\Program Files").lower()
                pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)").lower()
                if exe_dir.startswith(pf) or exe_dir.startswith(pf86):
                    cmd.append("ALLUSERS=1")
                    logger.info("Detected per-machine install, passing ALLUSERS=1")

                subprocess.Popen(cmd, close_fds=True)
                logger.info("Launched MSI installer: %s", path)
                return True

            if sys.platform == "linux":
                pkexec = shutil.which("pkexec")
                if pkexec:
                    subprocess.Popen(
                        [pkexec, "dpkg", "-i", str(path)],
                        close_fds=True,
                    )
                    logger.info("Launched DEB installer via pkexec: %s", path)
                    return True

                logger.warning("pkexec not found — manual install required")
                return False

        except Exception:
            logger.exception("Failed to launch installer")
        return False

    # -- private --

    def _on_timer(self) -> None:
        asyncio.ensure_future(self.check_for_update())
