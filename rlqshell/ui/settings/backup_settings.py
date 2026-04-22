"""Backup and restore settings page."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.config import ConfigManager
from rlqshell.app.constants import Colors
from rlqshell.core.backup_manager import BackupManager

logger = logging.getLogger(__name__)


class _BackupWorker(QThread):
    """Worker thread for creating a backup archive."""

    finished = Signal(str)
    error = Signal(str)

    def __init__(self, manager: BackupManager, dest: str, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._dest = dest

    def run(self) -> None:
        try:
            result = self._manager.create_backup(Path(self._dest))
            self.finished.emit(str(result))
        except Exception as exc:
            logger.exception("Backup failed")
            self.error.emit(str(exc))


class BackupSettings(QWidget):
    """Backup and restore settings panel."""

    def __init__(self, config: ConfigManager, sync_engine=None, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._sync_engine = sync_engine
        self._manager = BackupManager(config.data_dir)
        self._worker: _BackupWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Backup & Restore")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        layout.addWidget(title)

        # --- Backup section ---
        section_backup = QLabel("Create Backup")
        section_backup.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent; margin-top: 8px;"
        )
        layout.addWidget(section_backup)

        desc_backup = QLabel(
            "Save a full copy of your data (database, vault key, configuration) as a ZIP archive.\n"
            "The archive contains sensitive data — store it in a secure location."
        )
        desc_backup.setWordWrap(True)
        desc_backup.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        layout.addWidget(desc_backup)

        self._btn_backup = QPushButton("Create Backup…")
        self._btn_backup.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_backup.setFixedWidth(200)
        self._btn_backup.setStyleSheet(self._primary_btn_style())
        self._btn_backup.clicked.connect(self._on_backup)
        layout.addWidget(self._btn_backup)

        # --- Restore section ---
        section_restore = QLabel("Restore from Backup")
        section_restore.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent; margin-top: 16px;"
        )
        layout.addWidget(section_restore)

        desc_restore = QLabel(
            "Restore data from a previously created ZIP archive. Current data will be replaced.\n"
            "The application will close after restoring — restart it to apply the changes."
        )
        desc_restore.setWordWrap(True)
        desc_restore.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        layout.addWidget(desc_restore)

        self._btn_restore = QPushButton("Restore from Backup…")
        self._btn_restore.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_restore.setFixedWidth(200)
        self._btn_restore.setStyleSheet(self._danger_btn_style())
        self._btn_restore.clicked.connect(self._on_restore)
        layout.addWidget(self._btn_restore)

        layout.addStretch()

    def _on_backup(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Backup",
            "rlqshell_backup.zip",
            "ZIP Archive (*.zip)",
        )
        if not path:
            return

        self._btn_backup.setEnabled(False)
        self._btn_backup.setText("Creating backup…")

        self._worker = _BackupWorker(self._manager, path, self)
        self._worker.finished.connect(self._on_backup_done)
        self._worker.error.connect(self._on_backup_error)
        self._worker.start()

    def _on_backup_done(self, result_path: str) -> None:
        self._btn_backup.setEnabled(True)
        self._btn_backup.setText("Create Backup…")
        QMessageBox.information(
            self,
            "Backup Created",
            f"Backup saved successfully:\n{result_path}",
        )

    def _on_backup_error(self, message: str) -> None:
        self._btn_backup.setEnabled(True)
        self._btn_backup.setText("Create Backup…")
        QMessageBox.critical(
            self,
            "Backup Failed",
            f"Could not create backup:\n{message}",
        )

    def _on_restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Backup File",
            "",
            "ZIP Archive (*.zip)",
        )
        if not path:
            return

        zip_path = Path(path)

        if not BackupManager.is_valid_backup(zip_path):
            QMessageBox.critical(
                self,
                "Invalid File",
                "The selected file is not a valid RLQShell backup archive.",
            )
            return

        reply = QMessageBox.warning(
            self,
            "Restore Backup",
            "Your current data will be permanently replaced.\n\n"
            "Note: if cloud sync is active, it may re-apply newer cloud data on the next startup. "
            "To avoid this, disable cloud sync in Settings before restoring.\n\n"
            "Continue with restoring the backup?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            restored = self._manager.restore_backup(zip_path)
        except Exception as exc:
            logger.exception("Restore failed")
            QMessageBox.critical(
                self,
                "Restore Failed",
                f"Could not restore backup:\n{exc}",
            )
            return

        # If cloud sync is active, offer to push restored data to cloud.
        sync_active = (
            self._sync_engine is not None
            and self._sync_engine.provider is not None
            and self._sync_engine.provider.is_authenticated()
        )
        if sync_active:
            push = QMessageBox.question(
                self,
                "Upload Restored Data to Cloud?",
                "Cloud sync is active. Upload the restored data to the cloud now so it "
                "matches your local state?\n\n"
                "Choosing No will leave the cloud unchanged — the next sync may re-apply "
                "newer cloud data and override the restore.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if push == QMessageBox.StandardButton.Yes:
                self._btn_restore.setEnabled(False)
                self._btn_restore.setText("Uploading to cloud…")
                self._sync_engine.stop_auto_sync()
                self._config.set("sync.sync_on_close", False)
                self._sync_engine.sync_completed.connect(self._on_force_push_done)
                self._sync_engine.sync_error.connect(self._on_force_push_error)
                import asyncio
                asyncio.ensure_future(self._sync_engine.force_push())
                return

        self._quit_after_restore(restored)

    def _on_force_push_done(self, _stats) -> None:
        self._sync_engine.sync_completed.disconnect(self._on_force_push_done)
        self._sync_engine.sync_error.disconnect(self._on_force_push_error)
        QMessageBox.information(
            self,
            "Restore Complete",
            "Data restored and uploaded to cloud successfully.\n\n"
            "Please restart the application to apply the changes.",
        )
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    def _on_force_push_error(self, message: str) -> None:
        self._sync_engine.sync_completed.disconnect(self._on_force_push_done)
        self._sync_engine.sync_error.disconnect(self._on_force_push_error)
        self._btn_restore.setEnabled(True)
        self._btn_restore.setText("Restore from Backup…")
        logger.error("Force push after restore failed: %s", message)
        QMessageBox.warning(
            self,
            "Cloud Upload Failed",
            f"Data was restored locally but could not be uploaded to cloud:\n{message}\n\n"
            "The next sync may re-apply newer cloud data.",
        )

    def _quit_after_restore(self, restored: list[str]) -> None:
        files = "\n".join(f"  • {f}" for f in restored)
        QMessageBox.information(
            self,
            "Restore Complete",
            f"The following files were restored:\n{files}\n\n"
            "Please restart the application to apply the changes.",
        )
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    def _primary_btn_style(self) -> str:
        return (
            f"QPushButton {{"
            f"  background-color: {Colors.ACCENT}; color: #ffffff;"
            f"  border: none; border-radius: 6px;"
            f"  padding: 8px 16px; font-size: 13px; font-weight: 600;"
            f"}}"
            f"QPushButton:hover {{ background-color: {Colors.ACCENT_HOVER}; }}"
            f"QPushButton:disabled {{"
            f"  background-color: {Colors.BG_HOVER}; color: {Colors.TEXT_MUTED};"
            f"}}"
        )

    def _danger_btn_style(self) -> str:
        return (
            f"QPushButton {{"
            f"  background-color: {Colors.DANGER}; color: #ffffff;"
            f"  border: none; border-radius: 6px;"
            f"  padding: 8px 16px; font-size: 13px; font-weight: 600;"
            f"}}"
            f"QPushButton:disabled {{"
            f"  background-color: {Colors.BG_HOVER}; color: {Colors.TEXT_MUTED};"
            f"}}"
        )
