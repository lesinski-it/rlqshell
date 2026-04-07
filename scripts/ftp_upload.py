"""
FTP upload script dla pipeline CI/CD Gitea Actions.

Używanie:
    python scripts/ftp_upload.py <wersja>
    np.: python scripts/ftp_upload.py 0.1.0

Zmienne środowiskowe (Gitea Secrets):
    FTP_HOST      - adres serwera FTP (domyślnie: update.lesinski.it)
    FTP_USER      - nazwa użytkownika FTP
    FTP_PASS      - hasło FTP
    FTP_BASE_DIR  - (opcjonalnie) katalog bazowy na serwerze, nadpisuje wartość domyślną

Struktura docelowa na serwerze — jeden FTP user wspólny z RLQBackup,
RLQShell ląduje w katalogu obok (siostra dla rlqbackup):

    /home/lesinski_it_rlqbackup/public_html/
    ├── rlqbackup/            <- zarządzany przez pipeline RLQBackup
    └── rlqshell/             <- ten katalog
        ├── index.html
        ├── version.json      <- wgrywany JAKO OSTATNI (atomowość podmiany)
        └── releases/
            ├── RLQShell-0.1.0-x64.msi
            └── RLQShell-0.1.0.exe
"""

import ftplib
import os
import shutil
import sys


DEFAULT_FTP_BASE_DIR = "/home/lesinski_it_rlqbackup/public_html/rlqshell"
UPDATE_HOST = "update.lesinski.it"


def _ensure_dir(ftp: ftplib.FTP, path: str) -> None:
    """Tworzy katalog na FTP jeśli nie istnieje."""
    try:
        ftp.mkd(path)
        print(f"  Utworzono katalog: {path}")
    except ftplib.error_perm as e:
        if "550" in str(e):
            pass  # katalog już istnieje
        else:
            raise


def _upload_file(ftp: ftplib.FTP, local_path: str, remote_path: str) -> None:
    """Wgrywa plik na FTP z wyświetlaniem postępu."""
    file_size = os.path.getsize(local_path)
    uploaded = [0]

    def callback(data: bytes) -> None:
        uploaded[0] += len(data)
        pct = uploaded[0] * 100 // file_size
        mb_done = uploaded[0] / 1_048_576
        mb_total = file_size / 1_048_576
        print(
            f"\r  {os.path.basename(local_path)}: "
            f"{mb_done:.1f} / {mb_total:.1f} MB ({pct}%)",
            end="",
            flush=True,
        )

    with open(local_path, "rb") as f:
        ftp.storbinary(f"STOR {remote_path}", f, blocksize=65536, callback=callback)
    print()  # nowa linia po postępie


def main() -> None:
    if len(sys.argv) < 2:
        print("Użycie: python scripts/ftp_upload.py <wersja>", file=sys.stderr)
        sys.exit(1)

    version = sys.argv[1]

    host = os.environ.get("FTP_HOST", UPDATE_HOST)
    user = os.environ.get("FTP_USER")
    password = os.environ.get("FTP_PASS")
    base_dir = os.environ.get("FTP_BASE_DIR", DEFAULT_FTP_BASE_DIR)

    if not user or not password:
        print(
            "Błąd: brak zmiennych środowiskowych FTP_USER lub FTP_PASS",
            file=sys.stderr,
        )
        sys.exit(1)

    msi_local = f"dist/RLQShell-{version}-x64.msi"
    exe_local = f"dist/RLQShell-{version}.exe"
    # PyInstaller (rlqshell.spec) buduje dist/RLQShell.exe — kopiujemy z wersją w nazwie
    exe_src = "dist/RLQShell.exe"
    version_json_local = "dist/version.json"
    index_html_local = "dist/index.html"

    # Sprawdź czy pliki istnieją
    for path in [msi_local, exe_src, version_json_local, index_html_local]:
        if not os.path.exists(path):
            print(f"Błąd: plik nie istnieje: {path}", file=sys.stderr)
            sys.exit(1)

    # Kopiuj exe z wersją w nazwie
    shutil.copy2(exe_src, exe_local)

    releases_dir = f"{base_dir}/releases"

    print(f"Łączenie z FTP: {host}")
    with ftplib.FTP(host, user, password, timeout=60) as ftp:
        ftp.set_pasv(True)
        print(f"  Zalogowano jako: {user}")

        _ensure_dir(ftp, base_dir)
        _ensure_dir(ftp, releases_dir)

        # 1. Wgraj MSI
        print(f"Wgrywanie MSI (v{version})...")
        _upload_file(ftp, msi_local, f"{releases_dir}/RLQShell-{version}-x64.msi")

        # 2. Wgraj EXE
        print(f"Wgrywanie EXE (v{version})...")
        _upload_file(ftp, exe_local, f"{releases_dir}/RLQShell-{version}.exe")

        # 3. Wgraj index.html
        print("Wgrywanie index.html...")
        _upload_file(ftp, index_html_local, f"{base_dir}/index.html")

        # 4. Wgraj version.json JAKO OSTATNI (atomowość)
        print("Wgrywanie version.json...")
        _upload_file(ftp, version_json_local, f"{base_dir}/version.json")

    print(f"\nGotowe! Wersja {version} opublikowana na {host}.")
    print(f"Manifest: https://{host}/rlqshell/version.json")


if __name__ == "__main__":
    main()
