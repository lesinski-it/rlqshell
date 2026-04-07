# RLQShell — Modern Cross-Platform SSH Client
## Specyfikacja projektu i prompt developerski

---

## 1. Wizja projektu

**RLQShell** to nowoczesny, cross-platformowy (Linux, Windows, macOS) klient SSH
i manager połączeń zdalnych z naciskiem na **prywatność** i **suwerenność danych**.

Aplikacja stawia na: czysty, minimalistyczny interfejs z ciemnym motywem jako
domyślnym, płaską nawigację opartą o **Vaults → Hosts → Groups → Tags**, poziome
taby połączeń, wbudowany SFTP jako osobny tab, **Snippets** (zapisane komendy),
**Command Palette** (Ctrl+K), **Keychain** (zarządzanie kluczami SSH) i
**Port Forwarding** z GUI.

**USP — private cloud sync.** RLQShell synchronizuje hosty, klucze i hasła przez
**prywatną chmurę użytkownika** (Google Drive / Dropbox / OneDrive / Nextcloud).
Klucze, hasła i konfiguracja **nigdy nie opuszczają zaufanej infrastruktury
użytkownika** — nie ma centralnego serwera producenta, nie ma konta SaaS, nie ma
abonamentu. Vault jest szyfrowany lokalnie (Fernet/AES-256) zanim trafi do
chmury. Dodatkowo aplikacja jest **open-source** i wspiera **RDP, VNC, Telnet i
Serial** poza standardowym SSH.

**Motto:** *„Twoje klucze. Twoja chmura. Zero subskrypcji."*

---

## 2. Wzorce UX i nawigacji

### 2.1 Nawigacja
- **Poziome taby** u góry okna: `Vault` | `Connections` | `SFTP` | `Port Forwarding`
- Vault = centralne miejsce na Hosts, Groups, Snippets, Keychain, Known Hosts
- Connections = aktywne sesje terminala (taby w tabach)
- SFTP = osobne sesje transferu plików (nie sidebar, a pełny tab)
- Port Forwarding = lista aktywnych i zapisanych reguł PF

### 2.2 Hosts & Groups
- Host = zdefiniowane połączenie (label, adres, port, protocol, credentials, tags)
- Group = kolekcja Hostów z dziedziczeniem ustawień (np. wspólny jump host, identity)
- Zagnieżdżanie Groups (nested groups)
- Tagi (labels/colors) do szybkiego filtrowania
- Wyszukiwanie fuzzy po label, adresie, tagach

### 2.3 Command Palette
- `Ctrl+K` / `Cmd+K` — globalna paleta komend z fuzzy search
- Akcje: połącz z hostem, otwórz snippet, przełącz tab, ustawienia, nowy host
- `Ctrl+J` / `Cmd+J` — przełączanie między otwartymi tabami
- `Ctrl+T` / `Cmd+T` — nowe połączenie (quick connect)

### 2.4 Styl UI
- Dark theme domyślny w czterech wybieralnych paletach (patrz **§4a Theme palettes**),
  domyślna paleta **cyan/morska** podkreśla USP "private cloud"
- Zaokrąglone rogi, subtelne cienie, smooth animacje przejść
- Fonty: Inter/IBM Plex Sans (UI), JetBrains Mono/Fira Code (terminal)
- Ikony: Lucide-style (outline, monochromatyczne, kolorowane runtime przez `currentColor`)
- **Compact icon rail** po lewej (64 px): tylko ikony + tooltip-label po hover
- Hosty wyświetlane jako card-like rows: dwurzędowy layout (label + status,
  poniżej adres + outline tagi z dot markerem)
- NIE wygląda jak natywna aplikacja Qt — custom styled, nowoczesny, „app-like"

---

## 4a. Theme palettes

System motywów zbudowany jest wokół jednego pliku QSS (`rlqshell/ui/themes/dark.qss`)
z placeholderami `{ACCENT}`, `{BG_PRIMARY}` itd. oraz słownika palet w
[`rlqshell/ui/themes/palettes.py`](../rlqshell/ui/themes/palettes.py). Przy starcie
[`Colors.apply_palette()`](../rlqshell/app/constants.py) podmienia atrybuty klasy
`Colors`, a [`ThemeManager.apply_theme()`](../rlqshell/ui/themes/theme_manager.py)
renderuje template przed `app.setStyleSheet()`.

| Paleta    | ACCENT     | Charakter                              |
|-----------|------------|----------------------------------------|
| **cyan**  | `#06b6d4`  | (default) świeży, techniczny, "private cloud" |
| emerald   | `#10b981`  | terminal CRT vibe, retro green-on-black|
| amber     | `#f97316`  | ciepły, energetyczny                   |
| azure     | `#3b82f6`  | korporacyjny niebieski                 |

Wybór palety odbywa się w **Settings → Appearance → Palette**. Zmiana wymaga
restartu aplikacji (inline `setStyleSheet()` w widgetach nie są hot-swap-owalne).

---

## 3. Stos technologiczny

| Warstwa | Technologia | Uzasadnienie |
|---------|-------------|--------------|
| **GUI Framework** | **PySide6** (Qt 6, LGPL) + heavy QSS custom styling | Cross-platform; QSS pozwala na pełnowartościowy custom look |
| **Terminal backend** | **pyte** (VT100/xterm emulator) + custom `QWidget` renderer | Pełna kontrola nad renderingiem, brak zależności od VTE |
| **SSH** | **paramiko** | Stabilny, dojrzały, pełne SSH2 |
| **SFTP** | **paramiko.SFTPClient** | Wbudowany w paramiko |
| **RDP** | **FreeRDP** (subprocess: `xfreerdp`) | Standard branżowy, window embedding via XEmbed/QWindow |
| **VNC** | custom RFB client + QWidget renderer | Lekki, embedded w tab |
| **Telnet** | **telnetlib3** (asyncio) | Async telnet |
| **Serial** | **pyserial** | De facto standard |
| **Baza danych** | **SQLite** (via `sqlite3`) | Lekka, plikowa, zero config |
| **Szyfrowanie** | **cryptography** (Fernet/AES-256) + **keyring** | Master password + systemowy keyring |
| **Async** | **asyncio** + **qasync** (Qt-asyncio bridge) | Non-blocking I/O w GUI |
| **Packaging** | **PyInstaller** / **Nuitka** | Standalone binaries per platform |
| **Testy** | **pytest** + **pytest-qt** | Unit + GUI integration tests |

---

## 4. Architektura

```
rlqshell/
├── main.py                        # Entry point
├── app/
│   ├── __init__.py
│   ├── application.py             # QApplication, singleton, event loop setup
│   ├── config.py                  # Settings manager (JSON + defaults)
│   └── constants.py               # Wersja, ścieżki, defaults
│
├── core/
│   ├── __init__.py
│   ├── vault.py                   # Vault: kontener na hosts, groups, keys, snippets
│   ├── host_manager.py            # CRUD Hosts, Groups, Tags
│   ├── snippet_manager.py         # CRUD Snippets (komendy/skrypty)
│   ├── keychain.py                # SSH key management (generate, import, export)
│   ├── credential_store.py        # Szyfrowane hasła (Fernet + master password)
│   ├── known_hosts.py             # Known hosts management + GUI
│   ├── connection_pool.py         # Active connections tracking
│   ├── port_forward_manager.py    # PF rules: local, remote, dynamic
│   ├── history.py                 # Connection history + command history
│   ├── plugin_loader.py           # Protocol plugin registry
│   └── models/
│       ├── __init__.py
│       ├── host.py                # Host, Group, Tag dataclasses
│       ├── snippet.py             # Snippet, SnippetPackage
│       ├── credential.py          # Identity (username + auth method)
│       ├── connection.py          # AbstractConnection base
│       ├── port_forward.py        # PortForwardRule
│       └── ssh_key.py             # SSHKey (private, public, certificate)
│
├── protocols/
│   ├── __init__.py
│   ├── base.py                    # AbstractProtocol interface
│   ├── ssh/
│   │   ├── __init__.py
│   │   ├── connection.py          # SSH session (paramiko)
│   │   ├── terminal.py            # SSH terminal widget
│   │   ├── sftp_session.py        # SFTP operations
│   │   ├── tunnel.py              # SSH tunneling (L/R/D)
│   │   └── host_chain.py          # Jump host / bastion chaining
│   ├── rdp/
│   │   ├── __init__.py
│   │   ├── connection.py          # FreeRDP wrapper
│   │   └── widget.py              # Embedded RDP display
│   ├── vnc/
│   │   ├── __init__.py
│   │   ├── connection.py          # RFB protocol client
│   │   └── widget.py              # VNC framebuffer renderer
│   ├── telnet/
│   │   ├── __init__.py
│   │   ├── connection.py          # Async telnet
│   │   └── terminal.py            # Telnet terminal (reuses base)
│   └── serial/
│       ├── __init__.py
│       ├── connection.py          # pyserial wrapper
│       └── terminal.py            # Serial terminal
│
├── ui/
│   ├── __init__.py
│   ├── main_window.py             # Główne okno — top-level layout
│   ├── top_bar.py                 # Poziome taby nawigacji: Vault|Connections|SFTP|PF
│   ├── command_palette.py         # Ctrl+K overlay z fuzzy search
│   │
│   ├── vault/                     # === Vault view ===
│   │   ├── __init__.py
│   │   ├── vault_page.py          # Strona Vault z sidebar + content
│   │   ├── sidebar.py             # Lewy panel: Hosts, Snippets, Keychain, Known Hosts
│   │   ├── host_list.py           # Lista hostów z wyszukiwaniem, tagami, grupami
│   │   ├── host_editor.py         # Panel boczny (slide-in) do edycji hosta
│   │   ├── group_editor.py        # Edycja grupy
│   │   ├── snippet_list.py        # Lista snippetów
│   │   ├── snippet_editor.py      # Edycja snippeta
│   │   ├── keychain_view.py       # Lista kluczy SSH + generowanie
│   │   ├── known_hosts_view.py    # Lista known hosts
│   │   └── identity_editor.py     # Edycja identity (user + auth)
│   │
│   ├── connections/               # === Connections view ===
│   │   ├── __init__.py
│   │   ├── connections_page.py    # Strona z tabami połączeń
│   │   ├── tab_bar.py             # Horizontal tab bar (customowy, z ikonami + kolorami)
│   │   ├── terminal_widget.py     # Custom terminal renderer (pyte + QPainter)
│   │   ├── terminal_toolbar.py    # Pasek pod terminalem: snippet picker, side panel toggle
│   │   ├── split_view.py          # Split pane manager (H/V split)
│   │   ├── side_panel.py          # Side panel w terminalu: snippets, history, appearance
│   │   └── broadcast_bar.py       # Broadcast input to multiple terminals
│   │
│   ├── sftp/                      # === SFTP view ===
│   │   ├── __init__.py
│   │   ├── sftp_page.py           # SFTP sesje jako taby
│   │   ├── file_browser.py        # Dual-pane file browser (local ↔ remote)
│   │   ├── transfer_queue.py      # Progress transferów
│   │   └── file_editor.py         # Prosty edytor tekstu (podgląd pliku)
│   │
│   ├── port_forward/              # === Port Forwarding view ===
│   │   ├── __init__.py
│   │   ├── pf_page.py             # Lista reguł PF
│   │   └── pf_editor.py           # Tworzenie/edycja reguły PF
│   │
│   ├── settings/                  # === Settings ===
│   │   ├── __init__.py
│   │   ├── settings_dialog.py     # Okno ustawień
│   │   ├── general_settings.py    # Ogólne: język, startup, autosave
│   │   ├── terminal_settings.py   # Terminal: font, rozmiar, kursor, scrollback, bell
│   │   ├── appearance_settings.py # Motywy, kolory, transparencja
│   │   ├── keybinding_settings.py # Skróty klawiszowe
│   │   └── import_export.py       # Import/export danych
│   │
│   ├── widgets/                   # === Reusable components ===
│   │   ├── __init__.py
│   │   ├── fuzzy_search.py        # Fuzzy search input z wynikami
│   │   ├── tag_widget.py          # Colored tag pill
│   │   ├── slide_panel.py         # Animated slide-in side panel
│   │   ├── toast.py               # Toast notification
│   │   ├── badge.py               # Status badge (connected/disconnected)
│   │   ├── icon_button.py         # Icon-only button z tooltip
│   │   ├── toggle_switch.py       # iOS-style toggle
│   │   ├── breadcrumb.py          # Path breadcrumb (SFTP)
│   │   └── empty_state.py         # Empty state illustration + CTA
│   │
│   └── themes/
│       ├── dark.qss               # Dark theme (domyślny)
│       ├── light.qss              # Light theme
│       ├── nord.qss               # Nord theme
│       ├── dracula.qss            # Dracula theme
│       ├── catppuccin_mocha.qss   # Catppuccin Mocha
│       ├── terminal_schemes.json  # Schematy kolorów terminala (Solarized, Monokai, etc.)
│       └── theme_manager.py       # Ładowanie i przełączanie motywów
│
├── utils/
│   ├── __init__.py
│   ├── ssh_config_parser.py       # Parser ~/.ssh/config
│   ├── platform_utils.py          # OS-specific helpers
│   ├── logger.py                  # Structured logging
│   ├── crypto.py                  # Encryption helpers
│   └── updater.py                 # Auto-update (GitHub releases)
│
├── resources/
│   ├── icons/                     # SVG ikony (Lucide/Phosphor)
│   ├── fonts/                     # JetBrains Mono, Inter
│   ├── translations/              # i18n: pl_PL.json, en_US.json
│   ├── images/                    # Empty state illustrations, logo
│   └── default_config.json
│
├── tests/
│   ├── conftest.py
│   ├── test_vault.py
│   ├── test_host_manager.py
│   ├── test_credential_store.py
│   ├── test_ssh_connection.py
│   ├── test_sftp_session.py
│   ├── test_snippet_manager.py
│   ├── test_keychain.py
│   └── test_port_forward.py
│
├── pyproject.toml
├── requirements.txt
├── LICENSE                        # MIT
└── README.md
```

---

## 5. Model danych (SQLite)

```sql
-- === ORGANIZACJA ===

CREATE TABLE vaults (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL DEFAULT 'Personal',
    description TEXT,
    is_default BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE groups (
    id INTEGER PRIMARY KEY,
    vault_id INTEGER NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES groups(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    icon TEXT DEFAULT 'folder',
    color TEXT,                             -- hex color (#e94560)
    -- Dziedziczone ustawienia (nullable = nie nadpisane, użyj parent/default)
    default_identity_id INTEGER REFERENCES identities(id),
    default_jump_host_id INTEGER REFERENCES hosts(id),
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL DEFAULT '#6c757d'
);

-- === HOSTS ===

CREATE TABLE hosts (
    id INTEGER PRIMARY KEY,
    vault_id INTEGER NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
    group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL,
    label TEXT NOT NULL,                    -- display name
    address TEXT,                           -- IP or hostname
    protocol TEXT NOT NULL DEFAULT 'ssh'
        CHECK(protocol IN ('ssh','rdp','vnc','telnet','serial')),
    -- SSH settings
    ssh_port INTEGER DEFAULT 22,
    ssh_identity_id INTEGER REFERENCES identities(id),
    ssh_host_chain_id INTEGER REFERENCES hosts(id),  -- jump host
    ssh_startup_snippet_id INTEGER REFERENCES snippets(id),
    ssh_keep_alive INTEGER DEFAULT 60,     -- seconds, 0 = disabled
    ssh_agent_forwarding BOOLEAN DEFAULT 0,
    ssh_x11_forwarding BOOLEAN DEFAULT 0,
    ssh_compression BOOLEAN DEFAULT 0,
    -- RDP settings
    rdp_port INTEGER DEFAULT 3389,
    rdp_username TEXT,
    rdp_domain TEXT,
    rdp_resolution TEXT DEFAULT '1920x1080',
    rdp_color_depth INTEGER DEFAULT 32,
    rdp_audio BOOLEAN DEFAULT 0,
    rdp_clipboard BOOLEAN DEFAULT 1,
    rdp_drive_mapping TEXT,                -- JSON: [{"local":"/home","name":"Home"}]
    -- VNC settings
    vnc_port INTEGER DEFAULT 5900,
    vnc_quality TEXT DEFAULT 'auto'
        CHECK(vnc_quality IN ('auto','lan','broadband','low')),
    vnc_view_only BOOLEAN DEFAULT 0,
    -- Telnet settings
    telnet_port INTEGER DEFAULT 23,
    telnet_raw_mode BOOLEAN DEFAULT 0,
    -- Serial settings
    serial_port_path TEXT,                 -- /dev/ttyUSB0, COM3
    serial_baud_rate INTEGER DEFAULT 115200,
    serial_data_bits INTEGER DEFAULT 8,
    serial_stop_bits TEXT DEFAULT '1',
    serial_parity TEXT DEFAULT 'none'
        CHECK(serial_parity IN ('none','even','odd','mark','space')),
    serial_flow_control TEXT DEFAULT 'none'
        CHECK(serial_flow_control IN ('none','xonxoff','rtscts','dsrdtr')),
    -- Terminal appearance (per-host override)
    terminal_theme TEXT,                   -- null = use global default
    terminal_font TEXT,
    terminal_font_size INTEGER,
    -- Meta
    notes TEXT,
    color_label TEXT,                      -- hex color for quick visual ID
    last_connected TIMESTAMP,
    connect_count INTEGER DEFAULT 0,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE host_tags (
    host_id INTEGER REFERENCES hosts(id) ON DELETE CASCADE,
    tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (host_id, tag_id)
);

-- === IDENTITIES & KEYS ===

CREATE TABLE identities (
    id INTEGER PRIMARY KEY,
    vault_id INTEGER NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
    label TEXT NOT NULL,                   -- "admin@prod", "deploy-key"
    username TEXT NOT NULL,
    auth_type TEXT NOT NULL DEFAULT 'password'
        CHECK(auth_type IN ('password','key','key+passphrase','agent')),
    encrypted_password BLOB,              -- Fernet-encrypted
    ssh_key_id INTEGER REFERENCES ssh_keys(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ssh_keys (
    id INTEGER PRIMARY KEY,
    vault_id INTEGER NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    key_type TEXT NOT NULL
        CHECK(key_type IN ('rsa','ed25519','ecdsa','rsa-cert','ed25519-cert')),
    encrypted_private_key BLOB,           -- Fernet-encrypted PEM
    public_key TEXT,                       -- plain text public key
    encrypted_passphrase BLOB,            -- if key has passphrase
    fingerprint TEXT,                      -- SHA256 fingerprint
    bits INTEGER,                          -- key size (RSA: 2048/4096)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- === SNIPPETS ===

CREATE TABLE snippet_packages (
    id INTEGER PRIMARY KEY,
    vault_id INTEGER NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
    name TEXT NOT NULL,                    -- "Docker", "Nginx", "System"
    icon TEXT,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE snippets (
    id INTEGER PRIMARY KEY,
    vault_id INTEGER NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
    package_id INTEGER REFERENCES snippet_packages(id) ON DELETE SET NULL,
    name TEXT NOT NULL,                    -- "Update & Upgrade"
    script TEXT NOT NULL,                  -- "sudo apt update && sudo apt upgrade -y"
    description TEXT,
    run_as_sudo BOOLEAN DEFAULT 0,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- === PORT FORWARDING ===

CREATE TABLE port_forward_rules (
    id INTEGER PRIMARY KEY,
    vault_id INTEGER NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
    host_id INTEGER NOT NULL REFERENCES hosts(id) ON DELETE CASCADE,
    label TEXT,
    direction TEXT NOT NULL
        CHECK(direction IN ('local','remote','dynamic')),
    bind_address TEXT DEFAULT '127.0.0.1',
    local_port INTEGER NOT NULL,
    remote_host TEXT,                      -- null for dynamic
    remote_port INTEGER,                   -- null for dynamic
    auto_start BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- === KNOWN HOSTS ===

CREATE TABLE known_hosts (
    id INTEGER PRIMARY KEY,
    hostname TEXT NOT NULL,
    port INTEGER DEFAULT 22,
    key_type TEXT NOT NULL,
    host_key TEXT NOT NULL,                -- base64 encoded
    fingerprint TEXT,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- === HISTORY ===

CREATE TABLE connection_history (
    id INTEGER PRIMARY KEY,
    host_id INTEGER REFERENCES hosts(id) ON DELETE SET NULL,
    host_label TEXT,                       -- snapshot, bo host może być usunięty
    address TEXT,
    protocol TEXT,
    connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    disconnected_at TIMESTAMP,
    duration_seconds INTEGER
);

CREATE TABLE command_history (
    id INTEGER PRIMARY KEY,
    host_id INTEGER REFERENCES hosts(id) ON DELETE SET NULL,
    command TEXT NOT NULL,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- === INDEXES ===

CREATE INDEX idx_hosts_vault ON hosts(vault_id);
CREATE INDEX idx_hosts_group ON hosts(group_id);
CREATE INDEX idx_hosts_label ON hosts(label);
CREATE INDEX idx_hosts_address ON hosts(address);
CREATE INDEX idx_snippets_vault ON snippets(vault_id);
CREATE INDEX idx_connection_history_date ON connection_history(connected_at);
CREATE INDEX idx_command_history_cmd ON command_history(command);
```

---

## 6. Specyfikacja funkcjonalna

### 6.1 Vault (hub nawigacyjny)

Vault to główna strona aplikacji po uruchomieniu. Zawiera sidebar z sekcjami
i content area po prawej.

**Sidebar sekcje:**
- **Hosts** — lista wszystkich hostów i grup (domyślna sekcja)
- **Snippets** — zapisane komendy i skrypty
- **Keychain** — klucze SSH (generowanie, import, eksport)
- **Known Hosts** — lista znanych hostów z fingerprint
- **Port Forwarding** — zapisane reguły PF
- **History** — ostatnie połączenia

**Host list features:**
- Widok list / widok grid (toggle)
- Filtrowanie po: tagu, grupie, protokole, statusie (online/offline)
- Wyszukiwanie fuzzy (label, adres, tag, notatki)
- Sortowanie: nazwa, ostatnie połączenie, częstotliwość, data utworzenia
- Kliknięcie w host → otwiera slide-in Host Editor (panel z prawej strony)
- Double-click / Enter → natychmiastowe połączenie (otwiera tab w Connections)
- Context menu: Connect, Connect in Split, Edit, Duplicate, Move to Group, Delete, Copy SSH Link
- Multi-select → akcje masowe: Run Snippet, Delete, Move to Group, Apply Tag
- Drag & drop hostów między grupami
- „Add" dropdown button: New Host, New Group, Import from SSH Config

**Host Editor (slide-in panel):**
- Label, Address, Protocol selector (SSH/RDP/VNC/Telnet/Serial)
- Pola dynamicznie zmieniają się w zależności od protokołu
- Identity picker (dropdown: istniejące identities + „Create new")
- Tags (multi-select pills z kolorami)
- Jump Host / Host Chain (SSH: selektor innego hosta jako bastion)
- Startup Snippet (SSH: snippet do uruchomienia po połączeniu)
- Port Forwarding rules (inline lista z edycją)
- Terminal Appearance override (theme, font, font size — opcjonalne)
- Notes (multiline text)
- Auto-save (zmiany w Host Editor zapisują się automatycznie)

### 6.2 Connections (terminal tabs)

**Tab bar:**
- Poziome taby, scrollowalne jeśli jest ich więcej niż mieści ekran
- Każdy tab: ikona protokołu + label hosta + color dot z host_color_label
- Tab close (x), middle-click close
- Drag to reorder tabs
- Right-click: Close, Close Others, Close All, Reconnect, Split H, Split V, Duplicate
- „+" button na końcu tab bar → Quick Connect dialog / Command Palette

**Terminal widget:**
- Custom renderer: `pyte.Screen` → `QPainter` na `QWidget`
- Pełne VT100/xterm emulation (kolory 256, true color, mouse tracking)
- Scrollback buffer: konfigurowalny (domyślnie 10 000 linii)
- Zaznaczanie tekstu: mouse select → auto-copy (opcja) lub Ctrl+Shift+C
- Wklejanie: Ctrl+Shift+V lub middle-click
- Zmiana fontu: Ctrl+Plus/Minus/0
- Search in terminal: Ctrl+Shift+F (overlay search bar z highlight + prev/next)
- URL detection: klikalne linki (Ctrl+Click → open in browser)
- Bell: visual flash tab + optional system notification
- Unicode, emoji, ligatures (jeśli font wspiera — np. JetBrains Mono z ligatures)

**Side panel w terminalu (toggle: Ctrl+S):**
- Zakładki: Snippets | History | Appearance
- Snippets: lista snippetów z szybkim kliknięciem → wklej do terminala
- History: globalna historia komend z wyszukiwaniem
- Appearance: zmiana theme/font/size terminala na żywo bez opuszczania sesji

**Split View:**
- Ctrl+Shift+E = split vertical, Ctrl+Shift+O = split horizontal
- Każdy panel to osobna sesja (lub ta sama — opcja)
- Drag panel edges to resize
- Drag panel back to tab (unsplit)
- Broadcast mode: Ctrl+Shift+B → input wysyłany do wszystkich paneli w split view

**Autocomplete (terminal):**
- Sugestie na podstawie command history
- Path/directory autocomplete
- Konfigurowalny w Settings → Terminal → Autocomplete

### 6.3 SFTP (oddzielne taby plików)

SFTP w RLQShell to osobna pełnoprawna strona z tabami sesji SFTP — nie ukryta
w sidebar, każdy transfer ma własny tab z dwupanelową przeglądarką plików.

**Layout:**
- Tab bar z sesjami SFTP (per-host)
- Dual pane: Local ↔ Remote (opcjonalnie single pane)
- Breadcrumb nawigacja (klikalna ścieżka)
- Toolbar: Upload, Download, New Folder, Delete, Refresh, Toggle Hidden Files

**File browser:**
- Kolumny: Name, Size, Modified, Permissions, Owner
- Sortowanie po każdej kolumnie
- Icons per file type (folder, text, image, archive, binary, etc.)
- Context menu: Download, Upload, Open/Edit, Rename, Delete, Copy Path, Properties, Chmod
- Drag & drop: OS → SFTP (upload), SFTP → OS (download), SFTP pane ↔ SFTP pane (copy)
- Double-click folder → navigate; double-click file → download & open / inline preview

**Transfer queue:**
- Dolny panel: lista aktywnych i oczekujących transferów
- Kolumny: File, Direction (↑/↓), Size, Progress, Speed, Status
- Akcje: Pause, Resume, Cancel, Clear completed
- Concurrent transfers: konfigurowalny limit (domyślnie 3)

**Bookmarks:**
- Zapisane ścieżki per-host (np. /var/log, /etc/nginx, /home/app)
- Quick access z dropdown w breadcrumb

### 6.4 Port Forwarding

**Port Forwarding page:**
- Lista wszystkich reguł PF
- Kolumny: Label, Host, Direction, Local Port, Remote, Status (active/inactive)
- Toggle switch per reguła: start/stop
- „+ New Rule" → PF Editor dialog

**PF Editor:**
- Host selector (dropdown)
- Direction: Local / Remote / Dynamic (SOCKS5)
- Bind address (default: 127.0.0.1)
- Local port
- Remote host + remote port (disabled for Dynamic)
- Auto-start on connect (checkbox)

**PF Wizard:**
- Quick setup: wpisz `local_port:remote_host:remote_port` lub `D:port`
- Parsuje i tworzy regułę

### 6.5 Snippets

**Snippet list:**
- Grupowane w Snippet Packages (foldery)
- Snippet: name, script (multiline), description, run_as_sudo
- Execute: na bieżącym terminalu lub na wielu hostach (multi-target picker)
- AI-assist (opcjonalnie, w przyszłości): „Opisz co komenda ma robić → generuj snippet"

**Snippet Packages:**
- „Docker", „Nginx", „System", „Database" — organizacja snippetów
- Drag & drop snippetów między packages

### 6.6 Keychain

**Keychain view:**
- Lista kluczy SSH z metadanymi: label, type, bits, fingerprint, created
- Akcje: Generate New, Import (from file/clipboard), Export (public/private), Delete
- Key Generator dialog: type (Ed25519/RSA/ECDSA), bits (RSA: 2048/4096), passphrase
- Copy public key (one-click → clipboard)
- Push public key to host (select host → auto `ssh-copy-id` equivalent)

### 6.7 Settings

**Sekcje:**
- **General:** język (pl/en), startup behavior, auto-save interval, confirm on close
- **Terminal:** default font, size, cursor style (block/underline/bar), cursor blink, scrollback, bell type, ligatures on/off, autocomplete on/off
- **Appearance:** theme selector, terminal color scheme, custom QSS path, opacity
- **Keybindings:** lista skrótów z możliwością rebind (detect conflicts)
- **SSH:** default port, keep-alive interval, preferred ciphers, preferred key exchange
- **Import/Export:** import z ~/.ssh/config, PuTTY, MobaXterm, CSV; export encrypted/plaintext JSON

---

## 7. UI Layout — wireframe

```
┌──────────────────────────────────────────────────────────────────────────┐
│  [⚡ RLQShell]    [ Vault ]  [ Connections (3) ]  [ SFTP ]  [ PF ]      │
│                                                          [⚙] [👤] [─×] │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  === VAULT VIEW ===                                                      │
│                                                                          │
│ ┌─────────────┐ ┌──────────────────────────────────────────────────────┐ │
│ │ 🔍 Search   │ │  Hosts                              [+ Add ▾] [≡/⊞]│ │
│ │             │ │                                                      │ │
│ │ ▸ Hosts     │ │  ┌──────────────────────────────────────────────┐   │ │
│ │ ▸ Snippets  │ │  │ 📁 Production                               │   │ │
│ │ ▸ Keychain  │ │  │   🖥 web-1        10.0.1.10   SSH  [🟢]    │   │ │
│ │ ▸ Known Ho..│ │  │   🖥 web-2        10.0.1.11   SSH  [🟢]    │   │ │
│ │ ▸ Port Fwd  │ │  │   🖥 db-primary   10.0.1.20   SSH  [⚪]    │   │ │
│ │ ▸ History   │ │  │   🖥 rdp-win      10.0.1.30   RDP  [⚪]    │   │ │
│ │             │ │  │ 📁 Staging                                   │   │ │
│ │             │ │  │   🖥 staging-1     10.0.2.10   SSH  [⚪]    │   │ │
│ │             │ │  │ 📁 Home Lab                                  │   │ │
│ │             │ │  │   🖥 proxmox       192.168.1.5 SSH  [🟢]    │   │ │
│ │             │ │  │   🖥 nas           192.168.1.10 SSH [🟢]    │   │ │
│ │             │ │  │   🖥 mikrotik      192.168.1.1 Telnet [⚪]  │   │ │
│ │             │ │  │   🖥 esp32-serial  /dev/ttyUSB0 Serial [⚪] │   │ │
│ │             │ │  └──────────────────────────────────────────────┘   │ │
│ └─────────────┘ └──────────────────────────────────────────────────────┘ │
│                                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  === CONNECTIONS VIEW ===                                                │
│                                                                          │
│ ┌──────────────────────────────────────────────────────────────────────┐ │
│ │  [🟢 web-1] [🟢 db-primary] [🔵 rdp-win]  [+]                     │ │
│ ├──────────────────────────────────────────────────────────────────────┤ │
│ │                                                                      │ │
│ │  admin@web-1:~$ systemctl status nginx                               │ │
│ │  ● nginx.service - A high performance web server                     │ │
│ │    Loaded: loaded (/lib/systemd/system/nginx.service; enabled)        │ │
│ │    Active: active (running) since Mon 2026-03-26 10:00:00 CET        │ │
│ │                                                                      │ │
│ │  admin@web-1:~$ █                                                    │ │
│ │                                                                      │ │
│ │                                                            [Snippets]│ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│  [⟳ Connected: admin@web-1:22]  [Uptime: 01:23:45]  [UTF-8]  [🔒 PF:2]│
└──────────────────────────────────────────────────────────────────────────┘


  === COMMAND PALETTE (Ctrl+K overlay) ===

  ┌───────────────────────────────────────────┐
  │  🔍 Type a command or host name...        │
  │ ─────────────────────────────────────────  │
  │  🖥  web-1 — 10.0.1.10 (SSH)              │
  │  🖥  db-primary — 10.0.1.20 (SSH)         │
  │  📋  Update & Upgrade (snippet)            │
  │  ⚙  Settings                               │
  │  📂  New Host                               │
  │  🔑  Keychain                               │
  └───────────────────────────────────────────┘
```

---

## 8. Keyboard Shortcuts (domyślne, rebindable)

| Skrót | Akcja |
|-------|-------|
| `Ctrl+K` | Command Palette — wyszukaj host, snippet, akcję |
| `Ctrl+J` | Jump to tab — przełącz między otwartymi sesjami |
| `Ctrl+T` | New connection (Quick Connect) |
| `Ctrl+W` | Close current tab |
| `Ctrl+Tab` | Next tab |
| `Ctrl+Shift+Tab` | Previous tab |
| `Ctrl+Shift+E` | Split vertical |
| `Ctrl+Shift+O` | Split horizontal |
| `Ctrl+Shift+B` | Broadcast mode toggle |
| `Ctrl+Shift+F` | Search in terminal |
| `Ctrl+Shift+C` | Copy selection |
| `Ctrl+Shift+V` | Paste to terminal |
| `Ctrl+S` | Toggle side panel (Snippets/History/Appearance) |
| `Ctrl+Plus/Minus` | Font size +/- |
| `Ctrl+0` | Reset font size |
| `Ctrl+,` | Settings |
| `Ctrl+N` | New Host |
| `Ctrl+Shift+N` | New Snippet |
| `F5` | Reconnect |
| `F11` | Fullscreen |

---

## 9. Theming & Appearance

### Application themes (QSS):
- **Dark** (domyślny): tło `#1e1e2e`, surface `#2a2a3e`, accent `#7c3aed`, text `#cdd6f4`
- **Light**: tło `#f5f5f5`, surface `#ffffff`, accent `#6d28d9`, text `#1e1e2e`
- **Nord**: palette Nord
- **Dracula**: palette Dracula
- **Catppuccin Mocha**: palette Catppuccin

### Terminal color schemes (niezależne od app theme):
- Solarized Dark / Light
- Monokai
- Dracula
- Nord
- Gruvbox Dark / Light
- Catppuccin (Latte, Mocha)
- Tokyo Night / Day
- One Dark / One Light
- RLQShell Default (custom, ciepłe kolory)

### Personalizacja:
- Font terminala: JetBrains Mono (domyślny), Fira Code, Cascadia Code, Hack, Source Code Pro
- Font UI: Inter (domyślny), IBM Plex Sans
- Cursor: block / underline / bar, blink on/off
- Transparencja terminala: 0–30% (opcja)

---

## 10. Bezpieczeństwo

- **Master Password:** opcjonalny, szyfruje vault z credentialami (AES-256-GCM via Fernet, PBKDF2 key derivation)
- **OS Keyring:** master password w systemowym keyring (GNOME Keyring, KDE Wallet, macOS Keychain, Windows Credential Locker)
- **No plaintext passwords:** nigdy — zawsze encrypted blob w SQLite
- **Auto-lock:** po X minutach nieaktywności (konfigurowalny)
- **SSH Host Key Verification:** dialog first-connect z fingerprint, zapis w known_hosts
- **Key storage:** private keys zaszyfrowane Fernet w SQLite, nigdy plaintext na dysku
- **Session logs:** opcjonalne, per-host, zapisywane lokalnie w `~/.rlqshell/logs/`

---

## 11. Plugin system (protokoły)

```python
# protocols/base.py

from abc import ABC, abstractmethod
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal, QObject
from core.models.host import Host


class ProtocolMeta:
    """Metadane protokołu."""
    name: str              # "ssh"
    display_name: str      # "SSH"
    icon: str              # "terminal" (lucide icon name)
    default_port: int      # 22
    supports_sftp: bool    # True (only SSH)
    supports_tunneling: bool  # True (only SSH)


class AbstractProtocol(ABC):
    """Interfejs pluginu protokołu."""

    @abstractmethod
    def get_meta(self) -> ProtocolMeta: ...

    @abstractmethod
    def create_connection(self, host: Host) -> 'AbstractConnection': ...

    @abstractmethod
    def create_widget(self, connection: 'AbstractConnection') -> QWidget: ...

    @abstractmethod
    def get_editor_fields(self) -> list[dict]:
        """Pola specyficzne dla protokołu w Host Editor.
        Returns: [{"name": "port", "type": "int", "label": "Port", "default": 22}, ...]
        """
        ...

    def create_sftp_session(self, connection) -> 'SFTPSession | None':
        """Opcjonalny SFTP (tylko SSH). Domyślnie None."""
        return None


class AbstractConnection(QObject, ABC):
    """Lifecycle połączenia z sygnałami Qt."""

    connected = Signal()
    disconnected = Signal(str)       # reason
    error = Signal(str)
    data_received = Signal(bytes)
    title_changed = Signal(str)

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    def send(self, data: bytes) -> None: ...

    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    def resize(self, cols: int, rows: int) -> None: ...
```

---

## 12. Fazy rozwoju

### Faza 1 — MVP (5–7 tygodni)
> Działający SSH client z nowoczesnym UI, Vault, Hosts i SFTP.

- [ ] Scaffold projektu (pyproject.toml, architektura katalogów)
- [ ] Custom QSS dark theme — minimalistyczny "private cloud" look (cyan domyślny)
- [ ] Main window z top navigation bar (Vault | Connections | SFTP)
- [ ] Vault page: sidebar (Hosts, Snippets, Keychain) + host list
- [ ] Host Editor (slide-in panel): SSH fields, Identity picker, Tags
- [ ] Identity / Credential store z szyfrowaniem Fernet
- [ ] SSH connection via paramiko (password + key + agent auth)
- [ ] Terminal Widget (pyte backend + QPainter renderer)
- [ ] Connections page z horizontal tab bar
- [ ] SFTP page: file browser (remote), upload, download, delete, mkdir
- [ ] Known Hosts management (first-connect dialog)
- [ ] Command Palette (Ctrl+K) z fuzzy search hosts
- [ ] Settings dialog: terminal font/size, theme, keybindings
- [ ] Reusable widgets: fuzzy search, tag pills, slide panel, toast, badge

### Faza 2 — Core Features (4–6 tygodni)
> Split view, snippets, port forwarding, history, polish.

- [ ] Split view (H/V) w Connections
- [ ] Broadcast mode
- [ ] Snippets: CRUD, packages, execute on terminal, multi-target
- [ ] Port Forwarding: page, editor, wizard, auto-start
- [ ] Terminal side panel (Ctrl+S): snippets, history, appearance
- [ ] Command history (per-host + global)
- [ ] Connection history
- [ ] Host chaining / jump host
- [ ] Import from ~/.ssh/config
- [ ] Import/export (JSON, CSV)
- [ ] SFTP: dual pane, drag & drop, transfer queue, bookmarks
- [ ] Keychain: generate, import, export SSH keys
- [ ] Master Password + OS keyring
- [ ] Auto-reconnect (configurable retry)
- [ ] Session logging

### Faza 3 — Multi-Protocol (4–6 tygodni)
> RDP, VNC, Telnet, Serial — pluginowy loading.

- [ ] Plugin loader (scan protocols/, register)
- [ ] Telnet plugin (terminal reuse)
- [ ] Serial plugin (pyserial + terminal reuse)
- [ ] RDP plugin (FreeRDP embedded)
- [ ] VNC plugin (custom RFB + QWidget)
- [ ] Protocol-specific Host Editor fields
- [ ] Dodatkowe terminal color schemes
- [ ] Light theme, Nord, Dracula, Catppuccin QSS themes

### Faza 4 — Polish & Ship (3–4 tygodnie)
> Packaging, testy, docs, i18n.

- [ ] Tab detach (drag to new window)
- [ ] Terminal autocomplete (history-based)
- [ ] URL detection in terminal
- [ ] Multi-select hosts → Run Snippet on multiple
- [ ] Push public key to host (ssh-copy-id equivalent)
- [ ] PyInstaller packaging: Linux AppImage, Windows .exe, macOS .dmg
- [ ] CI/CD (GitHub Actions: lint, test, build)
- [ ] pytest + pytest-qt test suite
- [ ] i18n (polski, angielski)
- [ ] README, screenshots, docs
- [ ] Logo, branding, empty state illustrations

### Faza 5 — Nice-to-Have (ongoing)
- [ ] X11 forwarding
- [ ] MOSH protocol support
- [ ] Snippet AI assistant (opisz → generuj komendę)
- [ ] Network device discovery (scan subnet)
- [ ] SFTP sync (rsync-like)
- [ ] Optional cloud sync (self-hosted, encrypted)
- [ ] Mobile companion app (concept)
- [ ] Auto-update (GitHub Releases API)

---

## 13. Pliki konfiguracyjne

```
~/.rlqshell/
├── config.json              # Ustawienia aplikacji
├── rlqshell.db              # SQLite — cały stan (hosts, keys, snippets, history)
├── vault.key                # Encrypted master key (PBKDF2 + Fernet)
├── themes/                  # Custom QSS themes
├── logs/                    # Session logs
│   └── web-1_2026-03-26_10-00.log
├── plugins/                 # User-installed protocol plugins
└── backups/                 # Auto-backup DB
    └── rlqshell_2026-03-26.db
```

---

## 14. Zależności

```
# requirements.txt
PySide6>=6.7.0
paramiko>=3.5
cryptography>=43.0
keyring>=25.0
pyserial>=3.5
pyte>=0.8
qasync>=0.27                # asyncio ↔ Qt bridge
aiofiles>=24.0
appdirs>=1.4

# optional
telnetlib3>=2.0             # Telnet plugin
Pillow>=10.0                # VNC framebuffer rendering
```

**Systemowe (opcjonalne):**
- `xfreerdp3` — dla RDP plugin
- `xdotool` — window embedding na X11

---

## 15. Prompt do Claude Code / AI pair-programming

```
Jesteś senior Python developerem budującym RLQShell — nowoczesny,
cross-platformowy SSH client z naciskiem na prywatność i synchronizację
przez prywatną chmurę użytkownika (Google Drive / Dropbox / OneDrive).

Stack: Python 3.12+, PySide6 (Qt6) z heavy custom QSS styling,
paramiko, pyte, pyserial, asyncio + qasync.

Design guidelines:
- Dark theme w 4 wybieralnych paletach (cyan domyślny — podkreśla USP "private cloud").
- Zaokrąglone rogi, smooth transitions, monochromatyczne outline ikony (Lucide-style).
- Fonty Inter (UI) + JetBrains Mono (terminal).
- Compact 64-px icon rail po lewej zamiast tekstowego sidebara.
- Card-like host rows z dwurzędowym layoutem (label + status, address + outline tagi).
- NIE natywny Qt look. Każdy widget ma custom QSS.
- Navigation: horizontal top tabs (Vault | Connections | SFTP | Port Forwarding).
- Command Palette (Ctrl+K) z fuzzy search.
- Slide-in panels zamiast modal dialogów gdzie to możliwe.

Architecture:
- core/ = logika biznesowa (vault, hosts, credentials, snippets)
- protocols/ = pluginy protokołów (ssh, rdp, vnc, telnet, serial)
- ui/ = widgety Qt (vault/, connections/, sftp/, port_forward/, widgets/)
- Baza: SQLite. Szyfrowanie: cryptography Fernet.

Rules:
1. Type hints wszędzie. Docstrings Google style.
2. Async (asyncio + qasync) dla operacji I/O. NIGDY nie blokuj main thread.
3. Sygnały/Sloty Qt do komunikacji UI ↔ Core.
4. Każdy moduł core/ ma test w tests/.
5. Cross-platform: izoluj platform-specific kod w utils/platform_utils.py.
6. Error handling: graceful degradation z toast notifications w UI.
7. Auto-save: zmiany w Host Editor zapisują się automatycznie po debounce.

Aktualnie implementuję: [NAZWA MODUŁU]
Kontekst: [CO JUŻ JEST ZROBIONE]
Zadanie: [CO MA BYĆ ZAIMPLEMENTOWANE]
```

---

## 16. Licencja

**MIT License** — pełna swoboda użycia, modyfikacji i dystrybucji.

---

*Specyfikacja RLQShell v1.0 — wygenerowana 2026-03-26*
