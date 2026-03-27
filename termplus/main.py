"""Termplus entry point."""

from __future__ import annotations

import asyncio
import logging
import sys

logger = logging.getLogger(__name__)


def main() -> None:
    """Launch the Termplus application."""
    # Must import PySide6 before qasync
    from termplus.app.application import TermplusApplication
    from termplus.ui.main_window import MainWindow
    from termplus.utils.logger import setup_logging

    app = TermplusApplication(sys.argv)
    setup_logging(app.config.log_dir)

    logger.info("Starting Termplus…")

    # Apply theme
    from termplus.ui.themes.theme_manager import ThemeManager

    theme_mgr = ThemeManager()
    theme_name = app.config.get("appearance.theme", "dark")
    theme_mgr.apply_theme(app, theme_name)

    # Install qasync event loop BEFORE creating any widgets that need async
    import qasync

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Initialize database and vault
    from termplus.core.connection_pool import ConnectionPool
    from termplus.core.credential_store import CredentialStore
    from termplus.core.database import Database
    from termplus.core.keychain import Keychain
    from termplus.core.known_hosts import KnownHostsManager
    from termplus.core.sync.conflict_resolver import ConflictResolver
    from termplus.core.sync.sync_engine import SyncEngine
    from termplus.core.sync.sync_state import SyncState
    from termplus.core.vault import Vault
    from termplus.ui.command_palette import CommandPalette, PaletteItem
    from termplus.ui.connections.connections_page import ConnectionsPage
    from termplus.ui.settings.settings_dialog import SettingsDialog
    from termplus.ui.sftp.sftp_page import SFTPPage
    from termplus.ui.vault.vault_page import VaultPage

    db = Database(app.config.db_path)
    vault = Vault(db)
    vault.initialize()

    credential_store = CredentialStore(db, app.config.vault_key_path)
    keychain = Keychain(db, credential_store)
    known_hosts_mgr = KnownHostsManager(db)
    connection_pool = ConnectionPool()

    # Cloud sync
    sync_state = SyncState(app.config.data_dir / "sync_state.json")
    sync_engine = SyncEngine(
        app.config.data_dir, sync_state, ConflictResolver(),
    )

    window = MainWindow()

    # Install real Vault page
    vault_page = VaultPage(
        vault.hosts, keychain=keychain, known_hosts=known_hosts_mgr,
    )
    window.set_vault_page(vault_page)

    # Install Connections page
    connections_page = ConnectionsPage(
        vault.hosts, credential_store, keychain, connection_pool,
    )
    window.set_connections_page(connections_page)

    # Wire Vault → Connections
    vault_page.connect_requested.connect(connections_page.open_connection)

    # Install SFTP page
    sftp_page = SFTPPage(
        vault.hosts, credential_store, keychain, connection_pool,
    )
    window.set_sftp_page(sftp_page)

    # Update connection badge in top bar
    connections_page.connection_count_changed.connect(
        window.top_bar.set_connection_count
    )

    # Command Palette (Ctrl+K)
    palette = CommandPalette(window)

    def _build_palette_items() -> list[PaletteItem]:
        items: list[PaletteItem] = []
        for host in vault.hosts.list_hosts():
            items.append(PaletteItem(
                title=host.label or host.address,
                subtitle=f"{host.address}:{host.ssh_port}",
                category="Host",
                action=lambda hid=host.id: connections_page.open_connection(hid),
            ))
        items.append(PaletteItem(
            title="Settings", category="Action",
            action=lambda: SettingsDialog(app.config, window, sync_engine=sync_engine).exec(),
        ))
        items.append(PaletteItem(
            title="New Host", category="Action",
            action=lambda: (
                window.top_bar._on_nav_click(0),
                vault_page._host_list._on_new_host(),
            ),
        ))
        return items

    def _show_palette():
        palette.set_items(_build_palette_items())
        palette.show_palette()

    from PySide6.QtGui import QShortcut, QKeySequence

    shortcut_palette = QShortcut(QKeySequence("Ctrl+K"), window)
    shortcut_palette.activated.connect(_show_palette)

    # Settings shortcut (Ctrl+,)
    shortcut_settings = QShortcut(QKeySequence("Ctrl+,"), window)
    shortcut_settings.activated.connect(
        lambda: SettingsDialog(app.config, window, sync_engine=sync_engine).exec()
    )

    # Wire settings button in top bar
    window.top_bar.settings_requested.disconnect()
    window.top_bar.settings_requested.connect(
        lambda: SettingsDialog(app.config, window, sync_engine=sync_engine).exec()
    )

    window.show()

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
