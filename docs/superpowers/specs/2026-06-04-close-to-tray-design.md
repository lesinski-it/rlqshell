# Close-to-Tray Setting — Design Spec

**Date:** 2026-06-04
**Status:** Approved

## Overview

Add a setting in the General tab that controls whether closing the main window exits the application or minimizes it to the system tray.

## Configuration

- **Key:** `general.close_to_tray`
- **Type:** bool
- **Default:** `False` (current behavior — close exits the app)
- **Persistence:** via existing `ConfigManager.set()` + `save()`

## UI — GeneralSettings

File: `rlqshell/ui/settings/general_settings.py`

Add a new section "Window Behavior" below the existing "Confirmation Dialogs" section. The section contains one row:

- **Label:** "Minimize to tray on close"
- **Control:** `ToggleSwitch` bound to `general.close_to_tray`
- Style identical to existing toggles in this panel

## Tray Icon — MainWindow

File: `rlqshell/ui/main_window.py`

### New field
```python
_tray_icon: QSystemTrayIcon | None = None
```

### New method: `_ensure_tray_icon()`

Creates the tray icon lazily on first call. Subsequent calls are no-ops.

- Icon: application icon (`QApplication.windowIcon()`)
- Context menu:
  - "Show RLQShell" → `self.show(); self.raise_(); self.activateWindow()`
  - separator
  - "Quit" → runs cleanup callback then `QApplication.quit()` (no confirmation dialog)
- Double-click on tray icon → same as "Show RLQShell"
- Calls `tray.show()`

### Modified: `set_config(config)`

After storing config, if `general.close_to_tray` is `True`, call `_ensure_tray_icon()` so the icon is available from app start.

### Modified: `closeEvent(event)`

Existing flow (confirmation dialog → cleanup → quit) is preserved when `close_to_tray = False`.

New branch when `close_to_tray = True`:

1. Run existing confirmation dialog (if `confirm_close_app` is enabled) — gives user a chance to cancel
2. If confirmed (or confirmation disabled):
   - `event.ignore()`
   - `self.hide()`
   - `_ensure_tray_icon()` (creates icon if not yet created)

Quit from tray bypasses the confirmation dialog — the user explicitly chose "Quit" from the tray menu.

## Out of scope

- Tray icon badge / connection count
- Quick-connect from tray menu
- Start minimized to tray on launch
