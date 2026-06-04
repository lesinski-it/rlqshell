# Close-to-Tray Setting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Minimize to tray on close" toggle in General settings that hides the main window to the system tray instead of quitting.

**Architecture:** New config key `general.close_to_tray` drives a `QSystemTrayIcon` created lazily in `MainWindow`. `closeEvent` branches on the setting — minimize to tray or quit. The tray icon provides "Show RLQShell" and "Quit" actions.

**Tech Stack:** PySide6 (`QSystemTrayIcon`, `QMenu`), existing `ConfigManager`, existing `ToggleSwitch` widget.

---

### Task 1: Add default config key

**Files:**
- Modify: `rlqshell/resources/default_config.json`

- [ ] **Step 1: Add the key**

In `rlqshell/resources/default_config.json`, inside the `"general"` object, add after `"confirm_close_tab": true`:

```json
"general": {
    "language": "en",
    "confirm_close_app": true,
    "confirm_close_tab": true,
    "close_to_tray": false,
    "auto_save": true,
    "auto_save_interval": 1000,
    "startup_page": "vault"
},
```

- [ ] **Step 2: Verify existing config test still passes**

```
pytest tests/test_config.py -v
```

Expected: all green. The new key has a default so no existing assertions break.

- [ ] **Step 3: Commit**

```bash
git add rlqshell/resources/default_config.json
git commit -m "feat: add general.close_to_tray config key (default false)"
```

---

### Task 2: Add toggle in GeneralSettings

**Files:**
- Modify: `rlqshell/ui/settings/general_settings.py`
- Test: `tests/test_general_settings.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_general_settings.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_general_settings.py -v
```

Expected: FAIL — `AttributeError: 'GeneralSettings' object has no attribute '_close_to_tray'`

- [ ] **Step 3: Add "Window Behavior" section to GeneralSettings**

In `rlqshell/ui/settings/general_settings.py`, replace the final two lines:

```python
        layout.addLayout(form)
        layout.addStretch()
```

with:

```python
        layout.addLayout(form)

        # --- Window behavior section ---
        wb_label = QLabel("Window Behavior")
        wb_label.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent; margin-top: 8px;"
        )
        layout.addWidget(wb_label)

        wb_form = QFormLayout()
        wb_form.setSpacing(12)
        wb_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._close_to_tray = ToggleSwitch()
        self._close_to_tray.set_checked(config.get("general.close_to_tray", False))
        self._close_to_tray.toggled.connect(
            lambda v: self._save("general.close_to_tray", v)
        )
        wb_form.addRow(self._make_label("Minimize to tray on close"), self._close_to_tray)

        layout.addLayout(wb_form)
        layout.addStretch()
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_general_settings.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add rlqshell/ui/settings/general_settings.py tests/test_general_settings.py
git commit -m "feat: add close-to-tray toggle in General settings"
```

---

### Task 3: Tray icon and closeEvent in MainWindow

**Files:**
- Modify: `rlqshell/ui/main_window.py`
- Test: `tests/test_main_window_tray.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_main_window_tray.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_main_window_tray.py -v
```

Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute '_tray_icon'`

- [ ] **Step 3: Add `_tray_icon` field to `MainWindow.__init__`**

In `rlqshell/ui/main_window.py`, in `MainWindow.__init__`, after the line:

```python
        logger.info("MainWindow created with TopBar navigation")
```

add:

```python
        self._tray_icon: QSystemTrayIcon | None = None
```

The `QSystemTrayIcon` type annotation needs the import — add it to the top-level imports block. In the existing import block from `PySide6.QtWidgets`, the list already contains several items. Add `QMenu` and `QSystemTrayIcon`:

```python
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)
```

- [ ] **Step 4: Add `_ensure_tray_icon()` and `_restore_from_tray()` methods**

Add these two methods anywhere before `closeEvent` in the `MainWindow` class (e.g. after `set_cleanup_callback`):

```python
    def _ensure_tray_icon(self) -> None:
        """Create and show the system tray icon if it doesn't exist yet."""
        if self._tray_icon is not None:
            return

        tray = QSystemTrayIcon(self.windowIcon(), self)

        menu = QMenu()
        show_action = menu.addAction("Show RLQShell")
        show_action.triggered.connect(self._restore_from_tray)
        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self._quit)

        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()

        self._tray_icon = tray

    def _restore_from_tray(self) -> None:
        """Bring the window back from the tray."""
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._restore_from_tray()
```

- [ ] **Step 5: Extract `_quit()` helper from `closeEvent`**

Add this method to `MainWindow` (before `closeEvent`):

```python
    def _quit(self) -> None:
        """Schedule async cleanup then quit the application."""
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
```

- [ ] **Step 6: Update `closeEvent` to branch on `close_to_tray`**

Replace the existing `closeEvent` method (lines 252–291 in the original file) with:

```python
    def closeEvent(self, event) -> None:
        """Handle window close — confirm, then either quit or minimize to tray."""
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

        event.ignore()

        close_to_tray = config.get("general.close_to_tray", False) if config else False
        if close_to_tray:
            self.hide()
            self._ensure_tray_icon()
        else:
            self._quit()
```

- [ ] **Step 7: Update `set_config` to pre-create tray icon when setting is on**

In the existing `set_config` method, after `self._config = config`, add:

```python
        if config.get("general.close_to_tray", False):
            self._ensure_tray_icon()
```

The updated `set_config` becomes:

```python
    def set_config(self, config: ConfigManager) -> None:
        """Set the config manager for persistent settings."""
        self._config = config
        if config.get("general.close_to_tray", False):
            self._ensure_tray_icon()
        # Follow OS color scheme changes when appearance.theme is "auto".
        from PySide6.QtGui import QGuiApplication

        hints = QGuiApplication.styleHints()
        if hints is not None:
            try:
                hints.colorSchemeChanged.connect(self._on_system_color_scheme_changed)
            except Exception:  # noqa: BLE001 — older Qt may lack this signal
                logger.debug("colorSchemeChanged signal unavailable", exc_info=True)
```

- [ ] **Step 8: Run the tray tests**

```
pytest tests/test_main_window_tray.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 9: Run the full test suite**

```
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 10: Commit**

```bash
git add rlqshell/ui/main_window.py tests/test_main_window_tray.py
git commit -m "feat: minimize to tray on close when close_to_tray is enabled"
```
