"""
Generate dist/version.json and dist/index.html for release publishing.

Usage:
    python scripts/generate_release_assets.py <version>
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path


BASE_URL = "https://update.lesinski.it/rlqshell"
DIST_DIR = Path("dist")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def size_bytes(path: Path) -> int:
    return path.stat().st_size


def size_mb(path: Path) -> float:
    return round(size_bytes(path) / (1024 * 1024), 1)


def find_linux_deb(version: str) -> Path:
    candidates = sorted(DIST_DIR.glob(f"rlqshell_{version}_*.deb"))
    if not candidates:
        raise FileNotFoundError(f"Missing Linux package: dist/rlqshell_{version}_*.deb")

    for deb_file in candidates:
        if deb_file.name.endswith("_amd64.deb"):
            return deb_file
    return candidates[0]


def require(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return path


def deb_arch_from_filename(deb_path: Path) -> str:
    # Example: rlqshell_0.1.0_amd64.deb -> amd64
    name = deb_path.name
    if "_" not in name:
        return "unknown"
    return name.rsplit("_", 1)[1].replace(".deb", "")


def generate_version_json(version: str, exe: Path, msi: Path, deb: Path) -> str:
    deb_name = deb.name
    content = {
        "schema_version": 1,
        "version": version,
        "release_date": date.today().isoformat(),
        "minimum_version": "0.1.0",
        "release_notes": f"Wersja {version}",
        "downloads": {
            "msi": {
                "url": f"{BASE_URL}/releases/{msi.name}",
                "sha256": sha256(msi),
                "size_bytes": size_bytes(msi),
            },
            "exe": {
                "url": f"{BASE_URL}/releases/RLQShell-{version}.exe",
                "sha256": sha256(exe),
                "size_bytes": size_bytes(exe),
            },
            "deb": {
                "url": f"{BASE_URL}/releases/{deb_name}",
                "sha256": sha256(deb),
                "size_bytes": size_bytes(deb),
                "arch": deb_arch_from_filename(deb),
            },
        },
        "forced": False,
    }
    return json.dumps(content, ensure_ascii=False, indent=2)


def generate_index_html(version: str, exe: Path, msi: Path, deb: Path) -> str:
    exe_hash = sha256(exe)
    msi_hash = sha256(msi)
    deb_hash = sha256(deb)
    release_date = date.today().isoformat()
    deb_arch = deb_arch_from_filename(deb)

    return f"""<!DOCTYPE html>
<html lang="pl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RLQShell - Pobieranie</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #f0f2f5; color: #1a1a2e; min-height: 100vh; display: flex; align-items: center; justify-content: center; }}
    .container {{ max-width: 760px; width: 100%; margin: 2rem; background: #fff; border-radius: 12px; box-shadow: 0 2px 16px rgba(0,0,0,0.08); overflow: hidden; }}
    .header {{ background: linear-gradient(135deg, #0f3460, #16213e); color: #fff; padding: 2rem; text-align: center; }}
    .header h1 {{ font-size: 1.8rem; font-weight: 700; margin-bottom: 0.3rem; }}
    .header p {{ opacity: 0.85; font-size: 0.95rem; }}
    .version-badge {{ display: inline-block; background: rgba(255,255,255,0.15); border-radius: 20px; padding: 0.3rem 1rem; margin-top: 0.8rem; font-size: 0.9rem; }}
    .content {{ padding: 2rem; }}
    .download-card {{ border: 1px solid #e0e0e0; border-radius: 8px; padding: 1.2rem; margin-bottom: 1rem; transition: border-color 0.2s; }}
    .download-card:hover {{ border-color: #0f3460; }}
    .download-card h3 {{ font-size: 1rem; margin-bottom: 0.5rem; }}
    .download-card .meta {{ font-size: 0.82rem; color: #666; margin-bottom: 0.8rem; }}
    .download-card .sha {{ font-family: 'Consolas', monospace; font-size: 0.72rem; color: #888; word-break: break-all; background: #f8f8f8; padding: 0.4rem 0.6rem; border-radius: 4px; }}
    .btn {{ display: inline-block; background: #0f3460; color: #fff; text-decoration: none; padding: 0.6rem 1.5rem; border-radius: 6px; font-size: 0.9rem; font-weight: 600; transition: background 0.2s; }}
    .btn:hover {{ background: #1a4a8a; }}
    .footer {{ text-align: center; padding: 1rem 2rem 1.5rem; font-size: 0.8rem; color: #999; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>RLQShell</h1>
      <p>Klient SSH z synchronizacja przez prywatna chmure</p>
      <div class="version-badge">v{version} - {release_date}</div>
    </div>
    <div class="content">
      <div class="download-card">
        <h3>Windows MSI (zalecany)</h3>
        <div class="meta">Rozmiar: {size_mb(msi)} MB - instalacja systemowa z Menu Start i pulpitu</div>
        <a class="btn" href="releases/{msi.name}">Pobierz MSI</a>
        <div class="sha" style="margin-top:0.8rem">SHA256: {msi_hash}</div>
      </div>
      <div class="download-card">
        <h3>Windows EXE (portable)</h3>
        <div class="meta">Rozmiar: {size_mb(exe)} MB - uruchom bez instalacji</div>
        <a class="btn" href="releases/RLQShell-{version}.exe">Pobierz EXE</a>
        <div class="sha" style="margin-top:0.8rem">SHA256: {exe_hash}</div>
      </div>
      <div class="download-card">
        <h3>Linux DEB ({deb_arch})</h3>
        <div class="meta">Rozmiar: {size_mb(deb)} MB - Ubuntu, Debian, Mint, Pop!_OS</div>
        <a class="btn" href="releases/{deb.name}">Pobierz DEB</a>
        <div class="sha" style="margin-top:0.8rem">SHA256: {deb_hash}</div>
      </div>
    </div>
    <div class="footer">update.lesinski.it</div>
  </div>
</body>
</html>
"""


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/generate_release_assets.py <version>", file=sys.stderr)
        raise SystemExit(1)

    version = sys.argv[1]

    exe = require(DIST_DIR / "RLQShell.exe")
    msi = require(DIST_DIR / f"RLQShell-{version}-x64.msi")
    deb = find_linux_deb(version)

    version_json = generate_version_json(version, exe, msi, deb)
    index_html = generate_index_html(version, exe, msi, deb)

    (DIST_DIR / "version.json").write_text(version_json + "\n", encoding="utf-8")
    (DIST_DIR / "index.html").write_text(index_html, encoding="utf-8")

    print(f"Generated {DIST_DIR / 'version.json'}")
    print(f"Generated {DIST_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
