"""Dialog for changing remote file/directory permissions (chmod)."""

from __future__ import annotations

import asyncio

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import Colors
from rlqshell.protocols.ssh.sftp_session import SFTPSession

# (key, octal_bit) — key: u=user/owner, g=group, o=other; r/w/x=permission
_PERM_BITS = [
    ("ur", 0o400), ("uw", 0o200), ("ux", 0o100),
    ("gr", 0o040), ("gw", 0o020), ("gx", 0o010),
    ("or", 0o004), ("ow", 0o002), ("ox", 0o001),
]


class ChmodDialog(QDialog):
    """Permission editor for a remote file or directory."""

    def __init__(
        self,
        sftp: SFTPSession,
        path: str,
        current_mode: int,
        parent: QWidget | None = None,
        refresh_fn=None,
    ) -> None:
        super().__init__(parent)
        self._sftp = sftp
        self._path = path
        self._refresh_fn = refresh_fn
        self._updating = False

        self.setWindowTitle("Permissions")
        self.setModal(True)
        self.setMinimumWidth(340)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        path_label = QLabel(f"<b>{path}</b>")
        path_label.setWordWrap(True)
        path_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 12px;")
        layout.addWidget(path_label)

        grid_box = QGroupBox("Permissions")
        grid = QGridLayout(grid_box)
        grid.setSpacing(8)

        for col, header in enumerate(("Read", "Write", "Execute"), start=1):
            lbl = QLabel(header)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 11px;")
            grid.addWidget(lbl, 0, col)

        self._checks: dict[str, QCheckBox] = {}
        for row, (who, prefix) in enumerate(
            (("Owner", "u"), ("Group", "g"), ("Other", "o")), start=1
        ):
            lbl = QLabel(who)
            lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
            grid.addWidget(lbl, row, 0)
            for col, perm in enumerate(("r", "w", "x"), start=1):
                key = f"{prefix}{perm}"
                cb = QCheckBox()
                cb.stateChanged.connect(self._on_checkbox_changed)
                grid.addWidget(cb, row, col, alignment=Qt.AlignmentFlag.AlignCenter)
                self._checks[key] = cb

        layout.addWidget(grid_box)

        octal_row = QHBoxLayout()
        octal_row.addWidget(QLabel("Octal:"))
        self._octal_edit = QLineEdit()
        self._octal_edit.setFixedWidth(70)
        self._octal_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._octal_edit.setStyleSheet(
            f"font-family: 'JetBrains Mono', monospace; font-size: 13px; "
            f"color: {Colors.TEXT_PRIMARY};"
        )
        self._octal_edit.textEdited.connect(self._on_octal_edited)
        octal_row.addWidget(self._octal_edit)
        octal_row.addStretch()
        layout.addLayout(octal_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply)
        layout.addWidget(buttons)

        self._set_mode(current_mode & 0o777)

    def _set_mode(self, mode: int) -> None:
        self._updating = True
        for key, bit in _PERM_BITS:
            if key in self._checks:
                self._checks[key].setChecked(bool(mode & bit))
        self._octal_edit.setText(f"{mode:04o}")
        self._updating = False

    def _current_mode(self) -> int:
        mode = 0
        for key, bit in _PERM_BITS:
            if self._checks.get(key) and self._checks[key].isChecked():
                mode |= bit
        return mode

    def _on_checkbox_changed(self) -> None:
        if self._updating:
            return
        self._updating = True
        self._octal_edit.setText(f"{self._current_mode():04o}")
        self._updating = False

    def _on_octal_edited(self, text: str) -> None:
        if self._updating:
            return
        try:
            mode = int(text, 8) & 0o777
            self._set_mode(mode)
        except ValueError:
            pass

    def _apply(self) -> None:
        mode = self._current_mode()
        asyncio.ensure_future(self._do_chmod(mode))
        self.accept()

    async def _do_chmod(self, mode: int) -> None:
        from rlqshell.ui.widgets.toast import ToastManager

        try:
            await self._sftp.chmod(self._path, mode)
            ToastManager.instance().show_toast(
                f"Permissions changed to {mode:04o}", "success", duration_ms=3000
            )
            if self._refresh_fn is not None:
                await self._refresh_fn()
        except PermissionError:
            ToastManager.instance().show_toast("Permission denied", "error", duration_ms=5000)
        except Exception as exc:
            ToastManager.instance().show_toast(f"chmod failed: {exc}", "error", duration_ms=5000)
