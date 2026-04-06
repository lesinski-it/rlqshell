"""Termplus entry point."""

from __future__ import annotations

import asyncio
import logging
import sys
import time

logger = logging.getLogger(__name__)


def main() -> None:
    """Launch the Termplus application."""
    # Only the bare minimum before showing the splash: QApplication must exist first
    from termplus.app.application import TermplusApplication
    from termplus.app.constants import APP_VERSION
    from termplus.ui.splash_screen import SplashScreen
    from PySide6.QtWidgets import QApplication

    app = TermplusApplication(sys.argv)

    _SPLASH_MIN_SECS = 5.0

    splash = SplashScreen(APP_VERSION)
    splash.show()
    splash.raise_()
    QApplication.processEvents()
    _splash_shown_at = time.monotonic()

    # Now it's safe to do everything else
    from termplus.utils.logger import setup_logging
    setup_logging(app.config.log_dir)

    logger.info("Starting Termplus…")

    splash.update_progress(5, "Loading theme…")

    # Apply theme
    from termplus.ui.themes.theme_manager import ThemeManager

    theme_mgr = ThemeManager()
    theme_name = app.config.get("appearance.theme", "dark")
    ui_font = app.config.get("appearance.ui_font", "Inter")
    ui_font_size = app.config.get("appearance.ui_font_size", 13)
    theme_mgr.apply_theme(app, theme_name, ui_font=ui_font, ui_font_size=ui_font_size)

    # Install qasync event loop BEFORE creating any widgets that need async
    splash.update_progress(15, "Initializing event loop…")
    import qasync

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Initialize database and vault
    splash.update_progress(30, "Loading modules…")
    from termplus.core.connection_pool import ConnectionPool
    from termplus.core.credential_store import CredentialStore
    from termplus.core.database import Database
    from termplus.core.keychain import Keychain
    from termplus.core.history_manager import HistoryManager
    from termplus.core.known_hosts import KnownHostsManager
    from termplus.core.port_forward_manager import PortForwardManager
    from termplus.core.sync.conflict_resolver import ConflictResolver
    from termplus.core.sync.sync_engine import SyncEngine
    from termplus.core.sync.sync_state import SyncState
    from termplus.core.vault import Vault
    from termplus.ui.command_palette import CommandPalette, PaletteItem
    from termplus.ui.connections.connections_page import ConnectionsPage
    from termplus.ui.settings.settings_dialog import SettingsDialog
    from termplus.ui.sftp.sftp_page import SFTPPage
    from termplus.ui.top_bar import TopBar
    from termplus.ui.vault.vault_page import VaultPage

    splash.update_progress(55, "Opening database…")
    db = Database(app.config.db_path)

    splash.update_progress(65, "Unlocking vault…")
    vault = Vault(db)
    vault.initialize()

    credential_store = CredentialStore(db, app.config.vault_key_path)

    # Wait until minimum display time has elapsed, then close splash
    splash.update_progress(75, "Ready…")
    _remaining = _SPLASH_MIN_SECS - (time.monotonic() - _splash_shown_at)
    if _remaining > 0:
        _deadline = time.monotonic() + _remaining
        while time.monotonic() < _deadline:
            QApplication.processEvents()
    splash.close()

    # Master password dialog — unlock or set new password
    from termplus.ui.dialogs.master_password_dialog import MasterPasswordDialog

    mp_dialog = MasterPasswordDialog(credential_store)
    if mp_dialog.exec() != MasterPasswordDialog.DialogCode.Accepted:
        logger.info("Master password skipped")

    keychain = Keychain(db, credential_store)
    known_hosts_mgr = KnownHostsManager(db)
    history_mgr = HistoryManager(db)
    pf_mgr = PortForwardManager(db)
    connection_pool = ConnectionPool()

    # Cloud sync
    sync_state = SyncState(app.config.data_dir / "sync_state.json")
    sync_engine = SyncEngine(
        app.config.data_dir, sync_state, ConflictResolver(),
    )

    from termplus.ui.main_window import MainWindow
    window = MainWindow()
    window.set_config(app.config)
    window.apply_appearance(app.config)

    # Install real Vault page
    vault_page = VaultPage(
        vault.hosts,
        credential_store=credential_store,
        keychain=keychain,
        known_hosts=known_hosts_mgr,
        snippet_manager=vault.snippets,
        history_manager=history_mgr,
        pf_manager=pf_mgr,
        connection_pool=connection_pool,
    )
    window.set_vault_page(vault_page)

    # Install Connections page
    connections_page = ConnectionsPage(
        vault.hosts, credential_store, keychain, connection_pool,
        known_hosts=known_hosts_mgr, history_manager=history_mgr,
        config=app.config,
    )
    window.set_connections_page(connections_page)

    # Wire Vault → Connections / SFTP
    def _on_connect_requested(host_id: int) -> None:
        connections_page.open_connection(host_id)
        window.top_bar.navigate_to(TopBar.PAGE_CONNECTIONS)

    vault_page.connect_requested.connect(_on_connect_requested)

    def _open_sftp_from_vault(host_id: int) -> None:
        sftp_page.open_sftp_session(host_id)
        window.top_bar.navigate_to(TopBar.PAGE_SFTP)

    vault_page.sftp_requested.connect(_open_sftp_from_vault)

    def _on_snippet_run(script: str) -> None:
        if connections_page.send_to_active_terminal(script):
            window.top_bar.navigate_to(TopBar.PAGE_CONNECTIONS)
        else:
            from termplus.ui.widgets.toast import ToastManager
            ToastManager.instance().show_toast(
                "No active terminal — connect to a host first.",
            )

    vault_page.snippet_run_requested.connect(_on_snippet_run)

    def _on_snippet_broadcast(script: str) -> None:
        from termplus.ui.widgets.toast import ToastManager

        sessions = connections_page.get_terminal_sessions()
        if not sessions:
            ToastManager.instance().show_toast(
                "No active terminals — connect to a host first.",
            )
            return

        from termplus.ui.dialogs.snippet_target_dialog import SnippetTargetDialog

        dlg = SnippetTargetDialog(sessions, parent=window)
        if dlg.exec() != SnippetTargetDialog.DialogCode.Accepted:
            return
        selected = dlg.selected_tab_ids
        if not selected:
            return
        count = connections_page.send_to_terminals(script, selected)
        window.top_bar.navigate_to(TopBar.PAGE_CONNECTIONS)
        ToastManager.instance().show_toast(
            f"Snippet sent to {count} terminal(s).", toast_type="success",
        )

    vault_page.snippet_broadcast_requested.connect(_on_snippet_broadcast)

    def go_to_vault_hosts() -> None:
        """Navigate to the Vault and ensure the Hosts section is visible."""
        window.top_bar.navigate_to(TopBar.PAGE_VAULT)
        vault_page.go_to_section("hosts")

    # Install SFTP page
    sftp_page = SFTPPage(
        vault.hosts, credential_store, keychain, connection_pool,
        config=app.config, history_manager=history_mgr,
    )
    window.set_sftp_page(sftp_page)
    sftp_page.new_session_requested.connect(go_to_vault_hosts)

    # Update connection/SFTP counts in top bar
    connections_page.connection_count_changed.connect(
        window.top_bar.set_connection_count
    )
    sftp_page.session_count_changed.connect(
        window.top_bar.set_sftp_count
    )

    # Command Palette (Ctrl+K)
    palette = CommandPalette(window)

    def _open_settings():
        dlg = SettingsDialog(app.config, window, sync_engine=sync_engine)
        dlg.terminal_settings_changed.connect(connections_page.refresh_terminal_config)
        dlg.appearance_settings_changed.connect(
            lambda: window.apply_appearance(app.config)
        )
        dlg.exec()

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
            action=_open_settings,
        ))
        items.append(PaletteItem(
            title="New Host", category="Action",
            action=lambda: (
                window.top_bar.navigate_to(TopBar.PAGE_VAULT),
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
    shortcut_settings.activated.connect(_open_settings)

    # Keyboard shortcuts: Ctrl+W close tab, Ctrl+Tab/Ctrl+Shift+Tab switch tabs
    sc_close_tab = QShortcut(QKeySequence("Ctrl+W"), window)
    sc_close_tab.activated.connect(connections_page.close_current_tab)

    sc_next_tab = QShortcut(QKeySequence("Ctrl+Tab"), window)
    sc_next_tab.activated.connect(connections_page.next_tab)

    sc_prev_tab = QShortcut(QKeySequence("Ctrl+Shift+Tab"), window)
    sc_prev_tab.activated.connect(connections_page.prev_tab)

    # F11 fullscreen toggle — hides top bar + tab bar for immersive mode
    def _toggle_fullscreen():
        if window.isFullScreen():
            window.showNormal()
            window.top_bar.setVisible(True)
            window.set_fullscreen_bar_visible(False)
            connections_page.set_tab_bar_visible(True)
        else:
            window.top_bar.setVisible(False)
            connections_page.set_tab_bar_visible(False)
            window.top_bar.navigate_to(TopBar.PAGE_CONNECTIONS)
            window.showFullScreen()
            window.set_fullscreen_bar_visible(True)

    sc_fullscreen = QShortcut(QKeySequence("F11"), window)
    sc_fullscreen.activated.connect(_toggle_fullscreen)
    window.fullscreen_toggled.connect(_toggle_fullscreen)
    connections_page._tab_bar.fullscreen_requested.connect(_toggle_fullscreen)

    # Split view shortcuts
    sc_split_v = QShortcut(QKeySequence("Ctrl+Shift+E"), window)
    sc_split_v.activated.connect(connections_page.split_vertical)

    sc_split_h = QShortcut(QKeySequence("Ctrl+Shift+O"), window)
    sc_split_h.activated.connect(connections_page.split_horizontal)

    # Broadcast mode
    sc_broadcast = QShortcut(QKeySequence("Ctrl+Shift+B"), window)
    sc_broadcast.activated.connect(connections_page.toggle_broadcast)

    # Split picker (Ctrl+\)
    sc_split_picker = QShortcut(QKeySequence("Ctrl+\\"), window)
    sc_split_picker.activated.connect(lambda: connections_page.show_split_picker())

    # "+" button in tab bar → navigate to Vault to pick a host
    connections_page._tab_bar.new_tab_requested.connect(go_to_vault_hosts)

    # Wire settings button in top bar
    window.top_bar.settings_requested.disconnect()
    window.top_bar.settings_requested.connect(_open_settings)

    # Cleanup on close
    def _cleanup() -> None:
        logger.info("Cleaning up resources…")
        connection_pool.close_all()
        sync_engine.stop_auto_sync()
        credential_store.lock()
        vault.close()

    # Initialize toast manager
    from termplus.ui.widgets.toast import ToastManager

    ToastManager.instance().set_parent(window)

    window.set_cleanup_callback(_cleanup)

    window.show()

    screen = app.primaryScreen().availableGeometry()
    margin = 40
    new_w = min(window.width(), screen.width() - margin * 2)
    new_h = min(window.height(), screen.height() - margin * 2)
    window.resize(new_w, new_h)
    window.move(
        screen.x() + (screen.width() - new_w) // 2,
        screen.y() + (screen.height() - new_h) // 2,
    )

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
