<div align="center">

# RLQShell

**Cross-platform SSH client with private-cloud sync**

*Your keys. Your cloud. Zero subscription.*

[![Version](https://img.shields.io/badge/version-2.9.22-blue?style=flat-square)](https://update.lesinski.it/rlqshell/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12+-blue?style=flat-square)](pyproject.toml)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey?style=flat-square)]()

[Download](#download) · [Features](#features) · [Roadmap](#roadmap-2026) · [Support](#support-the-project)

</div>

---

## Features

### Protocols
- **SSH** — full VT100 terminal emulation, tabs, split panes
- **SFTP** — built-in file browser with upload, download and rename
- **RDP, VNC, Telnet, Serial** — all in one app

### Connection Management
- **Host Vault** — organize hosts into groups and tags with fast fuzzy search
- **Commands** — saved commands with variable substitution (`$VAR`, prompt on connect)
- **SSH Keychain** — generate, import and export SSH keys (RSA, Ed25519, ECDSA)
- **Tunelling** — local, remote and dynamic (SOCKS) rules with one-click toggle
- **Activity History** — recent hosts and per-session command history

### Private Cloud Sync
- End-to-end **AES-256 encryption** (Fernet) before any data leaves your machine
- Sync via **Google Drive**, **Dropbox** or **OneDrive** — your own account, no SaaS
- No central server, no vendor lock-in, no data collection

### UI / UX
- Dark theme with **4 color palettes** — Cyan, Emerald, Amber, Azure
- **Command Palette** (`Ctrl+K`) — fuzzy search over all actions and hosts
- Split terminal panes, session tabs, toast notifications
- Built-in auto-updater

---

## Download

Pre-built installers for Windows and Linux:

### **[➜ https://update.lesinski.it/rlqshell/](https://update.lesinski.it/rlqshell/)**

| Platform | Format | Requirements |
|----------|--------|--------------|
| Windows 10 / 11 | `.msi` installer | — |
| Debian / Ubuntu | `.deb` package | — |
| From source | `pip install` | Python ≥ 3.12 |

---

## Install from Source

```bash
git clone https://github.com/lesinski-it/rlqshell.git
cd rlqshell
pip install -e ".[all]"
rlqshell
```

Requires **Python 3.12+**. On Linux you may need Qt system libraries:

```bash
sudo apt install libglib2.0-0 libgl1
```

---

## Roadmap 2026

One feature shipped per month:

| Month | Feature |
|-------|---------|
| May 2026 | Google Drive Sync — stable sync with conflict resolution |
| June 2026 | Dropbox Sync — stable sync, unified provider API |
| August 2026 | SSH Jump Host / Bastion (ProxyJump) |
| October 2026 | macOS — App Bundle + DMG packaging |
| December 2026 | Linux — AppImage / Flatpak packaging |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| UI | PySide6 (Qt 6) + custom QSS theming |
| SSH | paramiko, async via qasync |
| Terminal | pyte VT100 rendered with QPainter |
| Crypto | cryptography (Fernet/AES-256), OS keyring |
| Storage | SQLite (local), Google Drive / Dropbox / OneDrive SDKs |
| Packaging | PyInstaller + WiX v6 (MSI), dpkg-deb (Debian) |

---

## Contributing

Pull requests are welcome. Please open an issue first to discuss larger changes.

```bash
# Run tests
pytest

# Lint
ruff check .
```

---

## Support the Project

RLQShell is free and open-source. If you find it useful, consider supporting the infrastructure and ongoing development:

### **[➜ https://lesinski.it/software/rlqshell](https://lesinski.it/software/rlqshell)**

---

## License

MIT © 2024–2026 Lesinski.it — see [LICENSE](LICENSE)
