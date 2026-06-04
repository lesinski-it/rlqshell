"""Tests for MainWindow tray-icon behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

from PySide6.QtWidgets import QSystemTrayIcon

from rlqshell.ui.main_window import MainWindow


def test_tray_icon_not_created_by_default(qtbot, tmp_config):
    window = MainWindow()
    qtbot.addWidget(window)
    window.set_config(tmp_config)
    assert window._tray_icon is None


def test_ensure_tray_icon_creates_icon(qtbot, tmp_config):
    window = MainWindow()
    qtbot.addWidget(window)
    window.set_config(tmp_config)
    window._ensure_tray_icon()
    assert isinstance(window._tray_icon, QSystemTrayIcon)


def test_ensure_tray_icon_is_idempotent(qtbot, tmp_config):
    window = MainWindow()
    qtbot.addWidget(window)
    window.set_config(tmp_config)
    window._ensure_tray_icon()
    first = window._tray_icon
    window._ensure_tray_icon()
    assert window._tray_icon is first


def test_set_config_creates_tray_when_enabled(qtbot, tmp_config):
    tmp_config.set("general.close_to_tray", True)
    window = MainWindow()
    qtbot.addWidget(window)
    window.set_config(tmp_config)
    assert isinstance(window._tray_icon, QSystemTrayIcon)


def test_restore_from_tray_shows_window(qtbot, tmp_config):
    window = MainWindow()
    qtbot.addWidget(window)
    window.set_config(tmp_config)
    window.hide()
    window._restore_from_tray()
    assert window.isVisible()


def test_close_event_tray_hides_window(qtbot, tmp_config):
    tmp_config.set("general.close_to_tray", True)
    window = MainWindow()
    qtbot.addWidget(window)
    window.set_config(tmp_config)
    window.show()
    # Simulate the close event without showing a dialog
    from PySide6.QtCore import QEvent
    event = QEvent(QEvent.Type.Close)
    window.closeEvent(event)
    assert not window.isVisible()
    assert isinstance(window._tray_icon, QSystemTrayIcon)


def test_quit_on_last_window_closed_disabled_when_tray_created(qtbot, tmp_config):
    from PySide6.QtWidgets import QApplication
    window = MainWindow()
    qtbot.addWidget(window)
    window.set_config(tmp_config)
    window._ensure_tray_icon()
    assert QApplication.instance().quitOnLastWindowClosed() is False


def test_tray_icon_hidden_on_close_when_feature_disabled(qtbot, tmp_config):
    # Enable tray first so icon is created
    tmp_config.set("general.close_to_tray", True)
    window = MainWindow()
    qtbot.addWidget(window)
    window.set_config(tmp_config)
    assert window._tray_icon is not None

    # Now disable the feature and simulate close
    tmp_config.set("general.close_to_tray", False)
    window.show()
    from PySide6.QtCore import QEvent
    event = QEvent(QEvent.Type.Close)
    window.closeEvent(event)
    assert window._tray_icon is None
