"""Main application window with TopBar navigation and page stack."""

from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.config import ConfigManager
from rlqshell.app.constants import APP_NAME, APP_VERSION, Colors, RESOURCES_DIR
from rlqshell.ui.top_bar import TopBar

logger = logging.getLogger(__name__)


class _PlaceholderPage(QWidget):
    """Temporary placeholder page until real pages are built."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        label = QLabel(title)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 16px;")
        layout.addWidget(label)


class MainWindow(QMainWindow):
    """RLQShell main window — TopBar + QStackedWidget for pages."""

    fullscreen_toggled = Signal()

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(QSize(1024, 700))
        self.resize(1280, 800)

        # Window icon — prefer .ico (Windows multi-res), fall back to .png, then .svg.
        images_dir = RESOURCES_DIR / "images"
        for icon_name in ("app_icon.ico", "app_icon.png", "logo.svg"):
            icon_path = images_dir / icon_name
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))
                break

        # Central widget
        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Fullscreen hint bar (hidden by default)
        self._fs_bar = QWidget()
        self._fs_bar.setFixedHeight(32)
        self._fs_bar.setStyleSheet(
            f"background-color: {Colors.ACCENT};"
        )
        fs_layout = QHBoxLayout(self._fs_bar)
        fs_layout.setContentsMargins(0, 0, 0, 0)
        fs_layout.setSpacing(0)
        fs_layout.addStretch()
        fs_label = QLabel("Press F11 to exit fullscreen")
        fs_label.setStyleSheet(
            "color: white; font-size: 12px; font-weight: 600; background: transparent;"
        )
        fs_layout.addWidget(fs_label)
        fs_layout.addSpacing(12)
        fs_exit_btn = QPushButton("Exit")
        fs_exit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fs_exit_btn.setStyleSheet(
            "QPushButton { color: white; background: rgba(255,255,255,0.2); "
            "border: 1px solid rgba(255,255,255,0.4); border-radius: 4px; "
            "padding: 2px 12px; font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { background: rgba(255,255,255,0.3); }"
        )
        fs_exit_btn.clicked.connect(lambda: self.fullscreen_toggled.emit())
        fs_layout.addWidget(fs_exit_btn)
        fs_layout.addStretch()
        self._fs_bar.setVisible(False)

        # Fade-out effect for fullscreen bar
        self._fs_opacity = QGraphicsOpacityEffect(self._fs_bar)
        self._fs_opacity.setOpacity(1.0)
        self._fs_bar.setGraphicsEffect(self._fs_opacity)

        self._fs_fade_anim = QPropertyAnimation(self._fs_opacity, b"opacity")
        self._fs_fade_anim.setDuration(600)
        self._fs_fade_anim.setStartValue(1.0)
        self._fs_fade_anim.setEndValue(0.0)
        self._fs_fade_anim.setEasingCurve(QEasingCurve.Type.InQuad)
        self._fs_fade_anim.finished.connect(lambda: self._fs_bar.setVisible(False))

        self._fs_hide_timer = QTimer(self)
        self._fs_hide_timer.setSingleShot(True)
        self._fs_hide_timer.setInterval(5000)
        self._fs_hide_timer.timeout.connect(self._fs_fade_anim.start)

        main_layout.addWidget(self._fs_bar)

        # Top navigation bar
        self._top_bar = TopBar()
        self._top_bar.page_changed.connect(self._on_page_changed)
        self._top_bar.settings_requested.connect(self._on_settings_requested)
        main_layout.addWidget(self._top_bar)

        # Page stack
        self._stack = QStackedWidget()
        self._vault_page = _PlaceholderPage("Vault — coming in Stage 4")
        self._connections_page = _PlaceholderPage("Connections — coming in Stage 6")
        self._sftp_page = _PlaceholderPage("SFTP — coming in Stage 7")
        self._pf_page = _PlaceholderPage("Port Forwarding — coming in Stage 8")

        self._stack.addWidget(self._vault_page)
        self._stack.addWidget(self._connections_page)
        self._stack.addWidget(self._sftp_page)
        self._stack.addWidget(self._pf_page)

        main_layout.addWidget(self._stack)
        self.setCentralWidget(central)

        logger.info("MainWindow created with TopBar navigation")

    @property
    def top_bar(self) -> TopBar:
        return self._top_bar

    @property
    def stack(self) -> QStackedWidget:
        return self._stack

    def set_vault_page(self, page: QWidget) -> None:
        """Replace the placeholder vault page with the real one."""
        self._stack.removeWidget(self._vault_page)
        self._vault_page.deleteLater()
        self._vault_page = page
        self._stack.insertWidget(TopBar.PAGE_VAULT, page)
        self._restore_stack_index()

    def set_connections_page(self, page: QWidget) -> None:
        """Replace the placeholder connections page."""
        self._stack.removeWidget(self._connections_page)
        self._connections_page.deleteLater()
        self._connections_page = page
        self._stack.insertWidget(TopBar.PAGE_CONNECTIONS, page)
        self._restore_stack_index()

    def set_sftp_page(self, page: QWidget) -> None:
        """Replace the placeholder SFTP page."""
        self._stack.removeWidget(self._sftp_page)
        self._sftp_page.deleteLater()
        self._sftp_page = page
        self._stack.insertWidget(TopBar.PAGE_SFTP, page)
        self._restore_stack_index()

    def set_port_forward_page(self, page: QWidget) -> None:
        """Replace the placeholder port forwarding page."""
        self._stack.removeWidget(self._pf_page)
        self._pf_page.deleteLater()
        self._pf_page = page
        self._stack.insertWidget(TopBar.PAGE_PORT_FORWARD, page)
        self._restore_stack_index()

    def _restore_stack_index(self) -> None:
        """Re-sync stack index with top bar after widget replacement."""
        self._stack.setCurrentIndex(self._top_bar._current_index)

    def _on_page_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        # Auto-refresh Port Forwarding page when navigated to
        if index == TopBar.PAGE_PORT_FORWARD and hasattr(self._pf_page, "refresh"):
            self._pf_page.refresh()
        logger.debug("Switched to page %d", index)

    def set_fullscreen_bar_visible(self, visible: bool) -> None:
        """Show or hide the fullscreen hint bar (auto-fades after 5 s)."""
        self._fs_hide_timer.stop()
        self._fs_fade_anim.stop()
        if visible:
            self._fs_opacity.setOpacity(1.0)
            self._fs_bar.setVisible(True)
            self._fs_hide_timer.start()
        else:
            self._fs_bar.setVisible(False)

    def _on_settings_requested(self) -> None:
        logger.info("Settings requested — dialog coming in Stage 8")

    def apply_appearance(self, config: ConfigManager) -> None:
        """Apply appearance settings (UI font, font size, window opacity)."""
        from rlqshell.ui.themes.theme_manager import ThemeManager, resolve_theme_setting

        app = QApplication.instance()
        if app:
            theme_name = resolve_theme_setting(config.get("appearance.theme", "auto"))
            # Re-apply palette before reloading the QSS so the template
            # placeholders pick up dark/light variant for the active palette.
            # Inline-styled widgets created earlier keep their old colors
            # until restart — see the restart hint in AppearanceSettings.
            Colors.apply_palette(
                config.get("appearance.palette", "amber"),
                theme=theme_name,
            )
            ui_font = config.get("appearance.ui_font", "Inter")
            ui_font_size = config.get("appearance.ui_font_size", 13)
            ThemeManager().apply_theme(app, theme_name, ui_font=ui_font, ui_font_size=ui_font_size)

        # Window opacity
        opacity = config.get("appearance.opacity", 100)
        self.setWindowOpacity(max(0.5, min(1.0, opacity / 100.0)))

    def set_config(self, config: ConfigManager) -> None:
        """Set the config manager for persistent settings."""
        self._config = config
        # Follow OS color scheme changes when appearance.theme is "auto".
        from PySide6.QtGui import QGuiApplication

        hints = QGuiApplication.styleHints()
        if hints is not None:
            try:
                hints.colorSchemeChanged.connect(self._on_system_color_scheme_changed)
            except Exception:  # noqa: BLE001 — older Qt may lack this signal
                logger.debug("colorSchemeChanged signal unavailable", exc_info=True)

    def _on_system_color_scheme_changed(self, _scheme) -> None:
        """Re-apply appearance when OS theme flips, but only if user is on auto."""
        config = getattr(self, "_config", None)
        if config is None:
            return
        if config.get("appearance.theme", "auto") == "auto":
            self.apply_appearance(config)

    def set_cleanup_callback(self, callback) -> None:
        """Register a callback to run on window close for resource cleanup."""
        self._cleanup_callback = callback

    def closeEvent(self, event) -> None:
        """Handle window close — confirm, then run cleanup callback."""
        config = getattr(self, "_config", None)
        confirm = config.get("general.confirm_close_app", True) if config else True

        if confirm:
            from PySide6.QtWidgets import QCheckBox
            msg = QMessageBox(self)
            msg.setWindowTitle("Exit RLQShell")
            msg.setText("Are you sure you want to quit?")
            msg.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            msg.setDefaultButton(QMessageBox.StandardButton.No)
            dont_ask = QCheckBox("Don't ask again")
            msg.setCheckBox(dont_ask)
            result = msg.exec()
            if dont_ask.isChecked() and config:
                config.set("general.confirm_close_app", False)
                config.save()
            if result != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        # Ignore the event now — we'll call QApplication.quit() after async cleanup.
        event.ignore()
        self.hide()
        logger.info("MainWindow closing")

        async def _run_cleanup_and_quit() -> None:
            if hasattr(self, "_cleanup_callback") and self._cleanup_callback:
                try:
                    result = self._cleanup_callback()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    logger.exception("Error during cleanup")
            QApplication.instance().quit()

        asyncio.ensure_future(_run_cleanup_and_quit())
