#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
DIST_DIR="${REPO_ROOT}/dist"
BUILD_DIR="${REPO_ROOT}/build/linux-deb"
PKG_ROOT="${BUILD_DIR}/pkgroot"

PACKAGE_NAME="rlqshell"
APP_NAME="RLQShell"
INSTALL_DIR="/opt/rlqshell"
DEFAULT_DEPENDS="libglib2.0-0, libgl1, libegl1, libxkbcommon0, libfontconfig1, libdbus-1-3, libx11-xcb1, libxcb1, libxcb-cursor0, libxrender1, libxext6, libxfixes3"

VERSION=""
ARCH=""
SKIP_PYINSTALLER="0"

usage() {
  cat <<'EOF'
Usage: installer/build-deb.sh [options]

Build RLQShell .deb package for Debian-based distributions.

Options:
  -v, --version <version>   Override package version (default: pyproject.toml)
  -a, --arch <arch>         Override package architecture (default: dpkg --print-architecture)
      --skip-pyinstaller    Skip PyInstaller build and package existing dist/RLQShell
  -h, --help                Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -v|--version)
      VERSION="$2"
      shift 2
      ;;
    -a|--arch)
      ARCH="$2"
      shift 2
      ;;
    --skip-pyinstaller)
      SKIP_PYINSTALLER="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

cd "${REPO_ROOT}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3.12+ first." >&2
  exit 1
fi

if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "dpkg-deb not found. Install dpkg first." >&2
  exit 1
fi

if [[ -z "${VERSION}" ]]; then
  VERSION="$(
    python3 - <<'PY'
import tomllib
from pathlib import Path

data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
print(data["project"]["version"])
PY
  )"
fi

if [[ -z "${ARCH}" ]]; then
  ARCH="$(dpkg --print-architecture)"
fi

if [[ "${SKIP_PYINSTALLER}" != "1" ]]; then
  if ! python3 -c "import PyInstaller" >/dev/null 2>&1; then
    echo "PyInstaller is not installed. Run: python3 -m pip install pyinstaller" >&2
    exit 1
  fi
  echo "==> Building Linux binary with PyInstaller"
  python3 -m PyInstaller --noconfirm --clean rlqshell.linux.spec
fi

BINARY_PATH="${DIST_DIR}/${APP_NAME}"
if [[ ! -f "${BINARY_PATH}" ]]; then
  echo "Missing ${BINARY_PATH}. Run without --skip-pyinstaller or build it manually." >&2
  exit 1
fi

ICON_SOURCE="${REPO_ROOT}/rlqshell/resources/images/logo.svg"
if [[ ! -f "${ICON_SOURCE}" ]]; then
  echo "Missing icon file: ${ICON_SOURCE}" >&2
  exit 1
fi

rm -rf "${BUILD_DIR}"
mkdir -p "${PKG_ROOT}/DEBIAN"
mkdir -p "${PKG_ROOT}${INSTALL_DIR}"
mkdir -p "${PKG_ROOT}/usr/bin"
mkdir -p "${PKG_ROOT}/usr/share/applications"
mkdir -p "${PKG_ROOT}/usr/share/icons/hicolor/scalable/apps"

install -m 0755 "${BINARY_PATH}" "${PKG_ROOT}${INSTALL_DIR}/${APP_NAME}"
install -m 0644 "${ICON_SOURCE}" "${PKG_ROOT}/usr/share/icons/hicolor/scalable/apps/rlqshell.svg"

# Sprawdź, czy plik docelowy istnieje przed utworzeniem symlinka
if [[ -f "${PKG_ROOT}${INSTALL_DIR}/${APP_NAME}" ]]; then
  ln -sf "${INSTALL_DIR}/${APP_NAME}" "${PKG_ROOT}/usr/bin/rlqshell"
else
  echo "ERROR: Plik docelowy dla symlinka nie istnieje: ${PKG_ROOT}${INSTALL_DIR}/${APP_NAME}" >&2
  exit 1
fi

cat > "${PKG_ROOT}/usr/share/applications/rlqshell.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=RLQShell
Comment=Modern SSH client with private-cloud sync
Exec=rlqshell %U
Icon=rlqshell
Terminal=false
Categories=Network;Utility;
Keywords=ssh;terminal;sftp;rdp;vnc;
StartupWMClass=RLQShell
EOF

cat > "${PKG_ROOT}/DEBIAN/control" <<EOF
Package: ${PACKAGE_NAME}
Version: ${VERSION}
Section: net
Priority: optional
Architecture: ${ARCH}
Maintainer: RLQShell Contributors <opensource@rlqshell.local>
Depends: ${DEFAULT_DEPENDS}
Description: Modern cross-platform SSH client with private-cloud sync
 RLQShell is a GUI client for SSH, SFTP, Telnet, Serial, VNC and RDP.
 It includes host management, key storage and optional cloud sync providers.
EOF

if [[ -f "${PKG_ROOT}${INSTALL_DIR}/${APP_NAME}" ]]; then
  chmod 0755 "${PKG_ROOT}${INSTALL_DIR}/${APP_NAME}"
else
  echo "WARNING: Plik wykonywalny nie istnieje: ${PKG_ROOT}${INSTALL_DIR}/${APP_NAME}" >&2
fi

if [[ -L "${PKG_ROOT}/usr/bin/rlqshell" ]]; then
  chmod 0755 "${PKG_ROOT}/usr/bin/rlqshell"
else
  echo "WARNING: Symlink nie istnieje: ${PKG_ROOT}/usr/bin/rlqshell" >&2
fi
chmod 0644 "${PKG_ROOT}/usr/share/applications/rlqshell.desktop"
chmod 0644 "${PKG_ROOT}/DEBIAN/control"

OUTPUT_DEB="${DIST_DIR}/${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
mkdir -p "${DIST_DIR}"

echo "==> Building ${OUTPUT_DEB}"
if dpkg-deb --help | grep -q -- '--root-owner-group'; then
  dpkg-deb --build --root-owner-group "${PKG_ROOT}" "${OUTPUT_DEB}"
else
  dpkg-deb --build "${PKG_ROOT}" "${OUTPUT_DEB}"
fi

echo "==> Done: ${OUTPUT_DEB}"
dpkg-deb --info "${OUTPUT_DEB}"
