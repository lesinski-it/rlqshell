"""
FTP upload script for Gitea Actions release pipeline.

Usage:
    python scripts/ftp_upload.py <version>
    e.g. python scripts/ftp_upload.py 0.1.0

Expected local files in dist/:
  - RLQShell-<version>-x64.msi
  - RLQShell.exe (copied to RLQShell-<version>.exe before upload)
  - rlqshell_<version>_<arch>.deb (at least one file, e.g. amd64)
  - index.html
  - version.json
"""

from __future__ import annotations

import ftplib
import glob
import os
import shutil
import sys
from pathlib import Path


DEFAULT_FTP_BASE_DIR = "/home/lesinski_it_rlqbackup/public_html/rlqshell"
UPDATE_HOST = "update.lesinski.it"


def _ensure_dir(ftp: ftplib.FTP, path: str) -> None:
    """Create remote directory if it does not exist."""
    try:
        ftp.mkd(path)
        print(f"  Created directory: {path}")
    except ftplib.error_perm as exc:
        if "550" not in str(exc):
            raise


def _upload_file(ftp: ftplib.FTP, local_path: str, remote_path: str) -> None:
    """Upload a single file with progress output."""
    file_size = os.path.getsize(local_path)
    uploaded = [0]

    def callback(data: bytes) -> None:
        uploaded[0] += len(data)
        pct = uploaded[0] * 100 // max(file_size, 1)
        mb_done = uploaded[0] / 1_048_576
        mb_total = file_size / 1_048_576
        print(
            f"\r  {os.path.basename(local_path)}: "
            f"{mb_done:.1f} / {mb_total:.1f} MB ({pct}%)",
            end="",
            flush=True,
        )

    with open(local_path, "rb") as file_obj:
        ftp.storbinary(f"STOR {remote_path}", file_obj, blocksize=65536, callback=callback)
    print()


def _required(path: str) -> None:
    if not os.path.exists(path):
        print(f"Error: missing required file: {path}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/ftp_upload.py <version>", file=sys.stderr)
        sys.exit(1)

    version = sys.argv[1]

    host = os.environ.get("FTP_HOST", UPDATE_HOST)
    user = os.environ.get("FTP_USER")
    password = os.environ.get("FTP_PASS")
    base_dir = os.environ.get("FTP_BASE_DIR", DEFAULT_FTP_BASE_DIR)

    if not user or not password:
        print("Error: missing FTP_USER or FTP_PASS environment variable", file=sys.stderr)
        sys.exit(1)

    msi_local = f"dist/RLQShell-{version}-x64.msi"
    exe_src = "dist/RLQShell.exe"
    exe_local = f"dist/RLQShell-{version}.exe"
    version_json_local = "dist/version.json"
    index_html_local = "dist/index.html"
    deb_files = sorted(glob.glob(f"dist/rlqshell_{version}_*.deb"))

    _required(msi_local)
    _required(exe_src)
    _required(version_json_local)
    _required(index_html_local)

    if not deb_files:
        print(
            f"Error: expected at least one Linux package: dist/rlqshell_{version}_*.deb",
            file=sys.stderr,
        )
        sys.exit(1)

    # PyInstaller creates dist/RLQShell.exe; publish a versioned filename.
    shutil.copy2(exe_src, exe_local)

    releases_dir = f"{base_dir}/releases"

    print(f"Connecting to FTP: {host}")
    with ftplib.FTP(host, user, password, timeout=60) as ftp:
        ftp.set_pasv(True)
        print(f"  Logged in as: {user}")

        _ensure_dir(ftp, base_dir)
        _ensure_dir(ftp, releases_dir)

        print(f"Uploading MSI (v{version})...")
        _upload_file(ftp, msi_local, f"{releases_dir}/{Path(msi_local).name}")

        print(f"Uploading EXE (v{version})...")
        _upload_file(ftp, exe_local, f"{releases_dir}/{Path(exe_local).name}")

        for deb_path in deb_files:
            print(f"Uploading DEB: {Path(deb_path).name} ...")
            _upload_file(ftp, deb_path, f"{releases_dir}/{Path(deb_path).name}")

        print("Uploading index.html...")
        _upload_file(ftp, index_html_local, f"{base_dir}/index.html")

        # Upload manifest last so clients see complete release atomically.
        print("Uploading version.json...")
        _upload_file(ftp, version_json_local, f"{base_dir}/version.json")

    print(f"\nDone. Version {version} published to {host}.")
    print(f"Manifest: https://{host}/rlqshell/version.json")


if __name__ == "__main__":
    main()
