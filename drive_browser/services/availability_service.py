"""
Availability service: checks whether indexed files physically exist on disk.
Performance optimization:
Uses os.scandir on each UNIQUE folder instead of calling os.stat / os.path.exists
on every individual file. This reduces disk I/O from 100,000+ system calls down to
a few hundred directory reads, finishing in seconds even on large external drives.
"""
from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional, Tuple, Callable

from PySide6.QtCore import QObject, QThread, Signal

from core.data_store import DataStore
from core.models import FileEntry

logger = logging.getLogger(__name__)


def check_availability_sync(
    data_store: DataStore,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    is_cancelled: Optional[Callable[[], bool]] = None
) -> Tuple[int, int]:
    """
    Synchronously verify existence of all entries using os.scandir per unique folder.
    Returns (available_count, unavailable_count).
    """
    # Group entries by folder path
    folder_map: Dict[str, List[FileEntry]] = {}
    for entry in data_store.entries:
        folder_map.setdefault(entry.folder, []).append(entry)

    total_folders = len(folder_map)
    available_count = 0
    unavailable_count = 0

    root_remap = data_store.root_remap
    orig_drive = data_store.original_drive

    report_interval = max(1, total_folders // 100)

    for i, (folder, entries) in enumerate(folder_map.items()):
        if is_cancelled and is_cancelled():
            break

        # Remap drive path if configured
        actual_folder = folder
        if root_remap and orig_drive and actual_folder.upper().startswith(orig_drive.upper()):
            actual_folder = root_remap + actual_folder[len(orig_drive):]

        actual_folder = os.path.abspath(actual_folder)

        # Check if folder itself exists
        if not os.path.isdir(actual_folder):
            for e in entries:
                e.is_available = False
            unavailable_count += len(entries)
        else:
            # Read all filenames in directory with single system call batch
            existing_filenames = set()
            try:
                with os.scandir(actual_folder) as it:
                    for dirent in it:
                        try:
                            if dirent.is_file():
                                existing_filenames.add(dirent.name.lower())
                        except OSError:
                            continue
            except OSError as err:
                logger.warning("Failed to scandir folder %s: %s", actual_folder, err)

            for e in entries:
                avail = e.name.lower() in existing_filenames
                e.is_available = avail
                if avail:
                    available_count += 1
                else:
                    unavailable_count += 1

        if progress_cb and (i % report_interval == 0 or i == total_folders - 1):
            progress_cb(i + 1, total_folders)

    return available_count, unavailable_count


class AvailabilityCheckThread(QThread):
    """
    Background worker thread for verifying file existence on storage.
    """
    progress = Signal(int, int)       # scanned_folders, total_folders
    finished = Signal(int, int)       # available_count, unavailable_count
    error_signal = Signal(str)

    def __init__(self, data_store: DataStore, parent=None):
        super().__init__(parent)
        self.data_store = data_store
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            avail, unavail = check_availability_sync(
                self.data_store,
                progress_cb=self._on_progress,
                is_cancelled=lambda: self._cancelled
            )
            if not self._cancelled:
                self.finished.emit(avail, unavail)
        except Exception as exc:
            logger.error("Availability check failed: %s", exc, exc_info=True)
            self.error_signal.emit(str(exc))

    def _on_progress(self, current: int, total: int):
        self.progress.emit(current, total)


class AvailabilityService(QObject):
    """
    High-level availability management service.
    """
    progress = Signal(int, int)
    finished = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: Optional[AvailabilityCheckThread] = None

    def check_availability(self, data_store: DataStore):
        if self._thread and self._thread.isRunning():
            self._thread.cancel()
            self._thread.wait()

        self._thread = AvailabilityCheckThread(data_store, self)
        self._thread.progress.connect(self.progress.emit)
        self._thread.finished.connect(self.finished.emit)
        self._thread.start()

    def cancel(self):
        if self._thread and self._thread.isRunning():
            self._thread.cancel()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()
