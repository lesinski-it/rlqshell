"""RLQShell entry point."""

from __future__ import annotations

import asyncio
import logging
import sys
import time

logger = logging.getLogger(__name__)


def main() -> None:
    """Launch the RLQShell application."""
    # Bare-minimum imports so the splash can appear as soon as humanly possible.
    # RLQShellApplication.__init__ is intentionally lean — fonts, icon and config
    # are loaded AFTER splash.show() so the user sees the loading window instantly.
    from PySide6.QtWidgets import QApplication

    from rlqshell.app.application import RLQShellApplication
    from rlqshell.app.constants import APP_VERSION
    from rlqshell.ui.splash_screen import SplashScreen

    app = RLQShellApplication(sys.argv)

    splash = SplashScreen(APP_VERSION)
    splash.show()
    splash.raise_()
    splash.update_progress(2, "Starting RLQShell\u2026")
    QApplication.processEvents()
    _splash_shown_at = time.monotonic()

    _splash_min_secs = 1.5

    # Window icon — fast, but still after splash so we don't delay it.
    app.load_window_icon()

    # Fonts — disk I/O for ~7 files. Report per-font progress so the bar moves.
    splash.update_progress(4, "Loading fonts\u2026")

    def _font_progress(index: int, total: int, name: str) -> None:
        # Spread font loading across 4–14% of the bar.
        pct = 4 + int(10 * (index + 1) / max(total, 1))
        splash.update_progress(pct, f"Loading {name}\u2026")

    app.load_fonts(progress_cb=_font_progress)

    splash.update_progress(15, "Initializing logging\u2026")
    from rlqshell.utils.logger import setup_logging
    setup_logging(app.config.log_dir)

    logger.info("Starting RLQShell…")

    splash.update_progress(20, "Loading theme\u2026")

    # Apply color palette BEFORE any widget is created — inline stylesheets
    # in widgets read Colors.* at __init__ time, so the palette must already
    # be active. Restart is required to change palette at runtime.
    from rlqshell.app.constants import Colors

    # Apply theme
    from rlqshell.ui.themes.theme_manager import ThemeManager, resolve_theme_setting

    theme_name = resolve_theme_setting(app.config.get("appearance.theme", "auto"))
    Colors.apply_palette(
        app.config.get("appearance.palette", "amber"),
        theme=theme_name,
    )

    theme_mgr = ThemeManager()
    ui_font = app.config.get("appearance.ui_font", "Inter")
    ui_font_size = app.config.get("appearance.ui_font_size", 13)
    theme_mgr.apply_theme(app, theme_name, ui_font=ui_font, ui_font_size=ui_font_size)

    # Install qasync event loop BEFORE creating any widgets that need async
    splash.update_progress(28, "Initializing event loop\u2026")
    import qasync

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Core modules — split into two import groups with progress between them
    # so the bar keeps moving during the heavy import phase.
    splash.update_progress(35, "Loading core modules\u2026")
    from rlqshell.core.connection_pool import ConnectionPool
    from rlqshell.core.credential_store import CredentialStore
    from rlqshell.core.database import Database
    from rlqshell.core.history_manager import HistoryManager
    from rlqshell.core.keychain import Keychain
    from rlqshell.core.known_hosts import KnownHostsManager
    from rlqshell.core.port_forward_manager import PortForwardManager
    from rlqshell.core.sync.conflict_resolver import ConflictResolver
    from rlqshell.core.sync.sync_engine import SyncEngine
    from rlqshell.core.sync.sync_state import SyncState
    from rlqshell.core.tunnel_engine import TunnelEngine
    from rlqshell.core.vault import Vault

    splash.update_progress(50, "Loading UI modules\u2026")
    from rlqshell.ui.command_palette import CommandPalette, PaletteItem
    from rlqshell.ui.connections.connections_page import ConnectionsPage
    from rlqshell.ui.port_forward.port_forward_page import PortForwardPage
    from rlqshell.ui.settings.settings_dialog import SettingsDialog
    from rlqshell.ui.sftp.sftp_page import SFTPPage
    from rlqshell.ui.top_bar import TopBar
    from rlqshell.ui.vault.vault_page import VaultPage

    splash.update_progress(62, "Opening database\u2026")
    db = Database(app.config.db_path)

    splash.update_progress(74, "Unlocking vault\u2026")
    vault = Vault(db)
    vault.initialize()

    splash.update_progress(85, "Initializing credentials\u2026")
    credential_store = CredentialStore(db, app.config.vault_key_path)

    # Smoothly animate 85% → 100% during the minimum-display window so the bar
    # actually looks like it's filling up instead of freezing on the last step.
    _remaining = _splash_min_secs - (time.monotonic() - _splash_shown_at)
    if _remaining > 0:
        _start = time.monotonic()
        _last_pct = 85
        while True:
            _elapsed = time.monotonic() - _start
            if _elapsed >= _remaining:
                break
            _pct = 85 + int(15 * _elapsed / _remaining)
            if _pct > _last_pct:
                splash.update_progress(_pct, "Almost ready\u2026")
                _last_pct = _pct
            else:
                QApplication.processEvents()
            time.sleep(0.016)  # ~60 fps

    splash.update_progress(100, "Ready")
    QApplication.processEvents()
    splash.close()

    # Master password dialog — unlock or set new password
    from rlqshell.ui.dialogs.master_password_dialog import MasterPasswordDialog

    mp_dialog = MasterPasswordDialog(credential_store)
    if mp_dialog.exec() != MasterPasswordDialog.DialogCode.Accepted:
        logger.info("Master password skipped")

    keychain = Keychain(db, credential_store)
    known_hosts_mgr = KnownHostsManager(db)
    history_mgr = HistoryManager(db)
    pf_mgr = PortForwardManager(db)
    connection_pool = ConnectionPool()
    tunnel_engine = TunnelEngine(vault.hosts, credential_store, keychain)

    # Cloud sync
    from rlqshell.core.sync.conflict_resolver import ConflictStrategy
    from rlqshell.core.sync.token_store import SyncTokenStore

    sync_state = SyncState(app.config.data_dir / "sync_state.json")

    # Resolve conflict strategy from config
    _strategy_map = {
        "last_write_wins": ConflictStrategy.LAST_WRITE_WINS,
        "keep_local": ConflictStrategy.KEEP_LOCAL,
        "keep_remote": ConflictStrategy.KEEP_REMOTE,
    }
    conflict_strategy = _strategy_map.get(
        app.config.get("sync.conflict_strategy", "last_write_wins"),
        ConflictStrategy.LAST_WRITE_WINS,
    )

    sync_engine = SyncEngine(
        app.config.data_dir,
        db,
        sync_state,
        ConflictResolver(conflict_strategy),
        cloud_folder=app.config.get("sync.cloud_folder", "/RLQShell"),
    )

    # Token persistence
    token_store = SyncTokenStore(db, credential_store)

    # Restore provider from saved tokens
    saved_provider_name = app.config.get("sync.provider", "None")
    if saved_provider_name and saved_provider_name != "None" and credential_store.is_unlocked:
        tokens = token_store.load_tokens(saved_provider_name)
        if tokens:
            try:
                proxy_url = None
                if app.config.get("sync.proxy_enabled", False):
                    proxy_url = app.config.get("sync.proxy_url", "").strip() or None
                from rlqshell.ui.settings.sync_settings import _create_provider

                provider = _create_provider(saved_provider_name, proxy_url)
                provider.set_tokens(tokens[0], tokens[1])
                if not provider.is_authenticated():
                    logger.info("Saved tokens expired for %s", saved_provider_name)
                    raise RuntimeError("saved tokens expired")
                sync_engine.set_provider(provider)
                sync_engine.set_token_save_callback(
                    lambda a, r: token_store.save_tokens(saved_provider_name, a, r)
                )

                if app.config.get("sync.auto_sync", False):
                    interval = app.config.get("sync.interval_minutes", 5)
                    sync_engine.start_auto_sync(interval)

                if app.config.get("sync.sync_on_start", False):
                    asyncio.ensure_future(sync_engine.sync())

                logger.info("Cloud sync restored for %s", saved_provider_name)
            except Exception:
                logger.warning("Could not restore cloud sync provider", exc_info=True)

    from rlqshell.ui.main_window import MainWindow
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

    if not credential_store.is_unlocked:
        window.top_bar.set_vault_locked(True)

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
            from rlqshell.ui.widgets.toast import ToastManager
            ToastManager.instance().show_toast(
                "No active terminal — connect to a host first.",
            )

    vault_page.snippet_run_requested.connect(_on_snippet_run)

    def _on_snippet_broadcast(script: str) -> None:
        from rlqshell.ui.widgets.toast import ToastManager

        sessions = connections_page.get_terminal_sessions()
        if not sessions:
            ToastManager.instance().show_toast(
                "No active terminals — connect to a host first.",
            )
            return

        from rlqshell.ui.dialogs.snippet_target_dialog import SnippetTargetDialog

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

    # Install Port Forwarding page
    pf_page = PortForwardPage(pf_mgr, tunnel_engine, vault.hosts)
    window.set_port_forward_page(pf_page)
    pf_page.navigate_to_vault.connect(go_to_vault_hosts)

    # Update connection/SFTP/tunnel counts in top bar
    connections_page.connection_count_changed.connect(
        window.top_bar.set_connection_count
    )
    sftp_page.session_count_changed.connect(
        window.top_bar.set_sftp_count
    )
    pf_page.tunnel_count_changed.connect(
        window.top_bar.set_tunnel_count
    )

    # Command Palette (Ctrl+K)
    palette = CommandPalette(window)

    # Auto-update manager
    from rlqshell.core.updater import UpdateManager

    update_manager = UpdateManager(app.config, parent=window)

    _pending_manifest: dict | None = None

    def _on_update_available(manifest: dict) -> None:
        nonlocal _pending_manifest
        from rlqshell.ui.dialogs.update_dialog import UpdateDialog

        # Manual check from Settings opens UpdateDialog directly — skip indicator.
        if getattr(update_manager, "_manual_check", False):
            update_manager._manual_check = False
            return

        version = manifest.get("version", "?")
        forced = manifest.get("_forced", False)

        if forced:
            dlg = UpdateDialog(manifest, update_manager, forced=True, parent=window)
            dlg.exec()
        else:
            _pending_manifest = manifest
            window.top_bar.set_update_available(version)

    def _on_update_icon_clicked() -> None:
        from rlqshell.ui.dialogs.update_dialog import UpdateDialog

        if _pending_manifest:
            dlg = UpdateDialog(_pending_manifest, update_manager, parent=window)
            dlg.exec()

    update_manager.update_available.connect(_on_update_available)
    window.top_bar.update_requested.connect(_on_update_icon_clicked)

    def _open_settings():
        dlg = SettingsDialog(
            app.config, window, sync_engine=sync_engine,
            update_manager=update_manager, token_store=token_store,
            credential_store=credential_store,
        )
        dlg.terminal_settings_changed.connect(connections_page.refresh_terminal_config)
        dlg.appearance_settings_changed.connect(
            lambda: window.apply_appearance(app.config)
        )
        dlg.exec()
        # Refresh cloud sync button visibility after settings may have changed provider
        window.top_bar.set_cloud_visible(_is_cloud_connected())

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

    from PySide6.QtGui import QKeySequence, QShortcut

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

    # Cloud sync quick-access button
    def _is_cloud_connected() -> bool:
        return (
            sync_engine.provider is not None
            and sync_engine.provider.is_authenticated()
        )

    window.top_bar.set_cloud_visible(_is_cloud_connected())

    def _on_quick_sync() -> None:
        asyncio.ensure_future(sync_engine.sync())

    window.top_bar.sync_requested.connect(_on_quick_sync)

    sync_engine.sync_started.connect(lambda: window.top_bar.set_cloud_syncing(True))
    sync_engine.sync_completed.connect(lambda _: window.top_bar.set_cloud_syncing(False))
    sync_engine.sync_error.connect(lambda _: window.top_bar.set_cloud_syncing(False))

    # Sync conflict → toast notification
    def _on_sync_conflict(filename: str, winner: str) -> None:
        from rlqshell.ui.widgets.toast import ToastManager

        ToastManager.instance().show_toast(
            f"Sync conflict: {filename} — kept {winner} version",
            toast_type="warning",
        )

    sync_engine.sync_conflict.connect(_on_sync_conflict)

    # Vault key changed during sync — re-derive key silently or prompt
    def _on_vault_key_changed() -> None:
        if credential_store.re_derive_key():
            logger.info("Vault key re-derived after sync (same password, new salt)")
            return

        # Password changed on remote device — must prompt
        credential_store.lock()
        window.top_bar.set_vault_locked(True)
        logger.info("Vault key changed on remote — prompting for re-unlock")

        from rlqshell.ui.dialogs.master_password_dialog import (
            MasterPasswordDialog as _MPD,
        )
        from rlqshell.ui.widgets.toast import ToastManager

        dlg = _MPD(credential_store, parent=window)
        if dlg.exec() == _MPD.DialogCode.Accepted:
            window.top_bar.set_vault_locked(False)
        else:
            ToastManager.instance().show_toast(
                "Vault locked — re-enter password to connect.",
                toast_type="warning",
            )

    sync_engine.vault_key_changed.connect(_on_vault_key_changed)

    def _on_sync_completed(stats: dict) -> None:
        from rlqshell.ui.vault.keychain_view import KeychainView
        from rlqshell.ui.widgets.toast import ToastManager

        added = stats.get("added", 0)
        updated = stats.get("updated", 0)
        deleted = stats.get("deleted", 0)
        pushed = stats.get("pushed", 0)

        # Refresh vault views when local DB changed
        if added or updated or deleted:
            vault_page._host_list.refresh()
            vault_page._refresh_identities()
            if isinstance(vault_page._keychain_section, KeychainView):
                vault_page._keychain_section.refresh()

        parts = []
        if added:
            parts.append(f"+{added} added")
        if updated:
            parts.append(f"~{updated} updated")
        if deleted:
            parts.append(f"-{deleted} deleted")
        if pushed:
            parts.append(f"↑{pushed} pushed")

        if parts:
            ToastManager.instance().show_toast(
                f"Sync: {', '.join(parts)}",
                toast_type="success",
            )

    sync_engine.sync_completed.connect(_on_sync_completed)

    # Cleanup on close
    async def _async_cleanup() -> None:
        """Run async cleanup tasks (sync on close, provider shutdown)."""
        if (
            app.config.get("sync.sync_on_close", False)
            and sync_engine.provider
            and sync_engine.provider.is_authenticated()
        ):
            try:
                await sync_engine.sync()
            except Exception:
                logger.warning("Sync on close failed", exc_info=True)
        try:
            await sync_engine.shutdown()
        except Exception:
            pass

    def _cleanup() -> None:
        logger.info("Cleaning up resources…")
        update_manager.stop()
        tunnel_engine.stop_all()
        connection_pool.close_all()

        # Schedule async cleanup — qasync loop is still running at this point
        future = asyncio.ensure_future(_async_cleanup())
        future.add_done_callback(lambda _: None)

        credential_store.lock()
        vault.close()

    # Initialize toast manager
    from rlqshell.ui.widgets.toast import ToastManager

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

    update_manager.start()

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
