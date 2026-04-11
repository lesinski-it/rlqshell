"""Update dialog — shows update info, downloads and installs the update."""

from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import APP_VERSION, Colors
from rlqshell.core.updater import UpdateManager

logger = logging.getLogger(__name__)


class UpdateDialog(QDialog):
    """Dialog presenting available update with download & install controls."""

    def __init__(
        self,
        manifest: dict,
        update_manager: UpdateManager,
        forced: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._manifest = manifest
        self._updater = update_manager
        self._forced = forced
        self._downloaded_path: str | None = None

        self.setWindowTitle("Update")
        self.setFixedSize(480, 340)
        self.setStyleSheet(f"QDialog {{ background-color: {Colors.BG_PRIMARY}; }}")

        if forced:
            self.setWindowFlags(
                Qt.WindowType.Dialog
                | Qt.WindowType.CustomizeWindowHint
                | Qt.WindowType.WindowTitleHint
            )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # title
        title = QLabel("Update available")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        layout.addWidget(title)

        # version info
        remote_ver = manifest.get("version", "?")
        ver_label = QLabel(f"v{APP_VERSION}  →  v{remote_ver}")
        ver_label.setStyleSheet(
            f"font-size: 14px; color: {Colors.ACCENT}; font-weight: 600; "
            f"background: transparent;"
        )
        layout.addWidget(ver_label)

        # release date + notes
        release_date = manifest.get("release_date", "")
        notes = manifest.get("release_notes", "")
        meta_parts = []
        if release_date:
            meta_parts.append(f"Release date: {release_date}")
        if notes:
            meta_parts.append(notes)
        if meta_parts:
            meta_label = QLabel("\n".join(meta_parts))
            meta_label.setWordWrap(True)
            meta_label.setStyleSheet(
                f"font-size: 12px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
            )
            layout.addWidget(meta_label)

        # download size
        dl_info = update_manager.get_download_info(manifest)
        if dl_info:
            size_mb = dl_info.get("size_bytes", 0) / (1024 * 1024)
            size_label = QLabel(f"Size: {size_mb:.1f} MB")
            size_label.setStyleSheet(
                f"font-size: 12px; color: {Colors.TEXT_MUTED}; background: transparent;"
            )
            layout.addWidget(size_label)

        layout.addStretch()

        # progress bar (hidden initially)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        self._progress.setFixedHeight(18)
        self._progress.setStyleSheet(
            f"QProgressBar {{ "
            f"  background-color: {Colors.BG_SURFACE}; "
            f"  border: 1px solid {Colors.BORDER}; border-radius: 4px; "
            f"  text-align: center; font-size: 11px; color: {Colors.TEXT_PRIMARY}; "
            f"}}"
            f"QProgressBar::chunk {{ "
            f"  background-color: {Colors.ACCENT}; border-radius: 3px; "
            f"}}"
        )
        layout.addWidget(self._progress)

        # status label
        self._status = QLabel("")
        self._status.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_MUTED}; background: transparent;"
        )
        self._status.setVisible(False)
        layout.addWidget(self._status)

        # buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._later_btn = QPushButton("Later")
        self._later_btn.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 6px; "
            f"padding: 8px 16px; font-size: 13px;"
        )
        self._later_btn.clicked.connect(self.reject)
        if forced:
            self._later_btn.setVisible(False)
        btn_row.addWidget(self._later_btn)

        self._update_btn = QPushButton("Update now")
        self._update_btn.setDefault(True)
        self._update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_btn.setStyleSheet(
            f"background-color: {Colors.ACCENT}; color: #ffffff; "
            f"border: none; border-radius: 6px; "
            f"padding: 8px 20px; font-size: 13px; font-weight: 600;"
        )
        self._update_btn.clicked.connect(self._on_update_clicked)
        btn_row.addWidget(self._update_btn)

        self._install_btn = QPushButton("Install and restart")
        self._install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._install_btn.setStyleSheet(
            f"background-color: {Colors.SUCCESS}; color: #ffffff; "
            f"border: none; border-radius: 6px; "
            f"padding: 8px 20px; font-size: 13px; font-weight: 600;"
        )
        self._install_btn.setVisible(False)
        self._install_btn.clicked.connect(self._on_install_clicked)
        btn_row.addWidget(self._install_btn)

        layout.addLayout(btn_row)

        # signals
        self._updater.download_progress.connect(self._on_progress)
        self._updater.download_complete.connect(self._on_download_complete)
        self._updater.download_failed.connect(self._on_download_failed)

    # -- slots --

    def _on_update_clicked(self) -> None:
        self._update_btn.setEnabled(False)
        self._update_btn.setText("Downloading…")
        self._later_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._status.setVisible(True)
        self._status.setText("Downloading update…")
        asyncio.ensure_future(self._updater.download_update(self._manifest))

    def _on_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            pct = int(downloaded * 100 / total)
            self._progress.setValue(pct)
            mb_done = downloaded / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            self._status.setText(f"Downloading… {mb_done:.1f} / {mb_total:.1f} MB")
        else:
            mb_done = downloaded / (1024 * 1024)
            self._status.setText(f"Downloading… {mb_done:.1f} MB")

    def _on_download_complete(self, path: str) -> None:
        self._downloaded_path = path
        self._progress.setValue(100)
        self._status.setText("Download complete — ready to install.")
        self._update_btn.setVisible(False)
        self._install_btn.setVisible(True)
        self._later_btn.setEnabled(True)

    def _on_download_failed(self, error: str) -> None:
        self._status.setText(f"Error: {error}")
        self._status.setStyleSheet(
            f"font-size: 12px; color: {Colors.DANGER}; background: transparent;"
        )
        self._update_btn.setEnabled(True)
        self._update_btn.setText("Retry")
        self._later_btn.setEnabled(True)
        self._progress.setVisible(False)

    def _on_install_clicked(self) -> None:
        if not self._downloaded_path:
            return
        ok = self._updater.launch_installer(self._downloaded_path)
        if ok:
            QApplication.quit()
        else:
            import sys
            if sys.platform == "linux":
                self._status.setText(
                    f"Install manually: sudo dpkg -i {self._downloaded_path}"
                )
            else:
                self._status.setText("Failed to launch the installer.")
            self._status.setStyleSheet(
                f"font-size: 12px; color: {Colors.WARNING}; background: transparent;"
            )

    # -- overrides --

    def closeEvent(self, event) -> None:
        if self._forced:
            event.ignore()
        else:
            super().closeEvent(event)

    def reject(self) -> None:
        if self._forced:
            return
        super().reject()
