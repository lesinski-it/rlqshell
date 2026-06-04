"""Tests for GeneralSettings panel."""

from __future__ import annotations

from rlqshell.ui.settings.general_settings import GeneralSettings


def test_close_to_tray_default_false(qtbot, tmp_config):
    widget = GeneralSettings(tmp_config)
    qtbot.addWidget(widget)
    assert widget._close_to_tray.is_checked() is False


def test_close_to_tray_reads_config(qtbot, tmp_config):
    tmp_config.set("general.close_to_tray", True)
    widget = GeneralSettings(tmp_config)
    qtbot.addWidget(widget)
    assert widget._close_to_tray.is_checked() is True


def test_close_to_tray_toggle_saves_config(qtbot, tmp_config):
    widget = GeneralSettings(tmp_config)
    qtbot.addWidget(widget)
    widget._close_to_tray.toggled.emit(True)
    assert tmp_config.get("general.close_to_tray") is True
