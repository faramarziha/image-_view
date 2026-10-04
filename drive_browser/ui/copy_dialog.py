"""
Copy dialog: shows progress, speed, ETA, and handles conflicts.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QRadioButton, QButtonGroup, QGroupBox,
    QCheckBox, QFileDialog, QTextEdit, QMessageBox,
)

from core.data_store import DataStore
from core.models import FileEntry
from services.copy_service import CopyThread, ConflictAction, CopyResult


class CopyDialog(QDialog):
    """
    Dialog for copying selected files with progress and conflict handling.
    """

    def __init__(
        self,
        data_store: DataStore,
        entry_indices: list[int],
        parent=None,
    ):
        super().__init__(parent)
        self._store = data_store
        self._indices = entry_indices
        self._copy_thread: CopyThread | None = None
        self.setWindowTitle("Copy Files")
        self.setMinimumSize(550, 400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Info
        info_label = QLabel(f"Ready to copy {len(self._indices):,} files")
        info_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(info_label)

        # Destination
        dest_layout = QHBoxLayout()
        dest_layout.addWidget(QLabel("Destination:"))
        self._dest_label = QLabel("Not selected")
        self._dest_label.setStyleSheet("color: #888;")
        dest_layout.addWidget(self._dest_label, 1)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_dest)
        dest_layout.addWidget(browse_btn)
        layout.addLayout(dest_layout)

        # Copy mode
        mode_group = QGroupBox("Copy Mode")
        mode_layout = QVBoxLayout(mode_group)
        radio_row = QHBoxLayout()
        self._structured_radio = QRadioButton("Preserve folder structure")
        self._structured_radio.setChecked(True)
        self._flat_radio = QRadioButton("Flat copy (all in one folder)")
        radio_row.addWidget(self._structured_radio)
        radio_row.addWidget(self._flat_radio)
        mode_layout.addLayout(radio_row)

        self._dedup_check = QCheckBox("In flat copy, copy duplicates with same name and size only once")
        self._dedup_check.setChecked(True)
        self._dedup_check.setEnabled(False)
        self._flat_radio.toggled.connect(self._dedup_check.setEnabled)
        mode_layout.addWidget(self._dedup_check)

        layout.addWidget(mode_group)

        # Conflict handling
        conflict_group = QGroupBox("Name Conflicts")
        conflict_layout = QHBoxLayout(conflict_group)
        self._skip_radio = QRadioButton("Skip")
        self._overwrite_radio = QRadioButton("Overwrite")
        self._rename_radio = QRadioButton("Auto-rename")
        self._rename_radio.setChecked(True)
        conflict_layout.addWidget(self._rename_radio)
        conflict_layout.addWidget(self._overwrite_radio)
        conflict_layout.addWidget(self._skip_radio)
        layout.addWidget(conflict_group)

        # Progress
        self._progress = QProgressBar()
        self._progress.setMinimum(0)
        self._progress.setMaximum(100)
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        # Status
        self._status_label = QLabel("Waiting to start...")
        self._status_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._status_label)

        # Error log
        self._error_log = QTextEdit()
        self._error_log.setMaximumHeight(100)
        self._error_log.setReadOnly(True)
        self._error_log.setVisible(False)
        self._error_log.setPlaceholderText("Errors will appear here...")
        layout.addWidget(self._error_log)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._start_btn = QPushButton("▶ Start Copy")
        self._start_btn.clicked.connect(self._start_copy)
        btn_layout.addWidget(self._start_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._cancel_copy)
        btn_layout.addWidget(self._cancel_btn)

        self._close_btn = QPushButton("Close")
        self._close_btn.clicked.connect(self.accept)
        self._close_btn.setVisible(False)
        btn_layout.addWidget(self._close_btn)

        layout.addLayout(btn_layout)

        self._dest_path = ''

    def _browse_dest(self):
        path = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if path:
            self._dest_path = path
            self._dest_label.setText(path)
            self._dest_label.setStyleSheet("color: #e0e0e0;")

    def _get_conflict_action(self) -> ConflictAction:
        if self._overwrite_radio.isChecked():
            return ConflictAction.OVERWRITE
        elif self._skip_radio.isChecked():
            return ConflictAction.SKIP
        return ConflictAction.RENAME

    def _start_copy(self):
        if not self._dest_path:
            QMessageBox.warning(self, "No Destination", "Please select a destination folder.")
            return

        entries = [self._store.entries[i] for i in self._indices]

        self._copy_thread = CopyThread(
            entries=entries,
            dest_dir=self._dest_path,
            flat_copy=self._flat_radio.isChecked(),
            root_remap=self._store.root_remap,
            original_drive=self._store.original_drive,
            dedup_same_name_size=self._dedup_check.isChecked(),
        )
        self._copy_thread.set_conflict_action(self._get_conflict_action(), for_all=True)
        self._copy_thread.progress.connect(self._on_progress)
        self._copy_thread.finished_ok.connect(self._on_finished)
        self._copy_thread.start()

        self._start_btn.setEnabled(False)
        self._status_label.setText("Copying...")

    def _on_progress(
        self,
        bytes_copied: int,
        total_bytes: int,
        filename: str,
        speed: float,
        eta: float,
        files_done: int = 0,
        total_files: int = 0
    ):
        if total_bytes > 0:
            self._progress.setValue(min(100, int(bytes_copied / total_bytes * 100)))

        speed_text = self._format_speed(speed)
        eta_text = self._format_time(eta)
        copied_text = self._format_size(bytes_copied)
        total_text = self._format_size(total_bytes)
        self._status_label.setText(
            f"File {files_done}/{total_files} ({copied_text}/{total_text}): {filename}  |  {speed_text}  |  ETA: {eta_text}"
        )

    def _on_finished(self, result: CopyResult):
        self._progress.setValue(100)

        if result.cancelled:
            status = f"Cancelled. Copied {result.copied}/{result.total} files."
        else:
            status = f"Done! Copied {result.copied}/{result.total} files."
            if result.skipped:
                status += f" Skipped: {result.skipped}."

        self._status_label.setText(status)

        if result.errors:
            self._error_log.setVisible(True)
            for path, err in result.errors:
                self._error_log.append(f"❌ {path}: {err}")

        self._start_btn.setVisible(False)
        self._cancel_btn.setVisible(False)
        self._close_btn.setVisible(True)

    def _cancel_copy(self):
        if self._copy_thread and self._copy_thread.isRunning():
            self._copy_thread.cancel()
            self._status_label.setText("Cancelling...")
        else:
            self.reject()

    @staticmethod
    def _format_size(num_bytes: int | float) -> str:
        if num_bytes < 1024:
            return f"{num_bytes:.0f} B"
        elif num_bytes < 1024 * 1024:
            return f"{num_bytes / 1024:.1f} KB"
        elif num_bytes < 1024 * 1024 * 1024:
            return f"{num_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"

    @staticmethod
    def _format_speed(bps: float) -> str:
        if bps < 1024:
            return f"{bps:.0f} B/s"
        elif bps < 1024 * 1024:
            return f"{bps / 1024:.1f} KB/s"
        else:
            return f"{bps / (1024 * 1024):.1f} MB/s"

    @staticmethod
    def _format_time(seconds: float) -> str:
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            return f"{seconds / 60:.0f}m {seconds % 60:.0f}s"
        else:
            return f"{seconds / 3600:.0f}h {(seconds % 3600) / 60:.0f}m"

    def closeEvent(self, event):
        if self._copy_thread and self._copy_thread.isRunning():
            self._copy_thread.cancel()
            self._copy_thread.wait(3000)
        event.accept()
