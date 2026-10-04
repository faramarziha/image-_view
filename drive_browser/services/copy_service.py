"""
Copy service: copies selected files to a destination with byte-level progress,
chunked streaming (1MB), mid-file cancellation cleanup, source/destination collision checks,
Windows filename sanitization, and flat-copy deduplication.
"""
from __future__ import annotations

import os
import re
import shutil
import time
from enum import Enum
from typing import Optional, Set, Tuple, List

from PySide6.QtCore import QThread, Signal

from core.models import FileEntry


class ConflictAction(Enum):
    SKIP = 'skip'
    OVERWRITE = 'overwrite'
    RENAME = 'rename'


# Invalid characters and reserved names for Windows filesystems
_INVALID_WIN_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
}

CHUNK_SIZE = 1024 * 1024  # 1 MB


def sanitize_windows_filename(name: str, replacement: str = "_") -> str:
    """
    Sanitize a filename for Windows compatibility:
    - Replaces invalid characters (<>:"/\\|?* and control chars)
    - Strips trailing dots and spaces from stems, extensions, and final filename
    - Escapes reserved device names (CON, NUL, AUX, etc.)
    """
    if not name:
        return "unnamed"
    base, ext = os.path.splitext(name)
    clean_base = _INVALID_WIN_CHARS.sub(replacement, base).strip(' .')
    clean_ext = _INVALID_WIN_CHARS.sub(replacement, ext).strip(' ')
    if not clean_base:
        clean_base = "file"
    if clean_base.upper() in _RESERVED_NAMES:
        clean_base = f"_{clean_base}"
    result = (clean_base + clean_ext).rstrip(' .')
    return result if result else "file"


def is_subpath(parent: str, child: str) -> bool:
    """Check if child path is inside or identical to parent path."""
    try:
        p = os.path.abspath(parent).lower().rstrip('\\/')
        c = os.path.abspath(child).lower().rstrip('\\/')
        if p == c:
            return True
        common = os.path.commonpath([p, c]).lower()
        return common == p
    except (ValueError, OSError):
        return False


class CopyResult:
    """Result of a copy operation."""
    __slots__ = ('total', 'total_bytes', 'copied', 'copied_bytes', 'skipped', 'errors', 'cancelled')

    def __init__(self):
        self.total: int = 0
        self.total_bytes: int = 0
        self.copied: int = 0
        self.copied_bytes: int = 0
        self.skipped: int = 0
        self.errors: List[Tuple[str, str]] = []  # (file_path, error_msg)
        self.cancelled: bool = False


class CopyThread(QThread):
    """
    Background thread for chunked file copying with byte-level progress reporting.

    Signals:
        progress(bytes_copied, total_bytes, current_filename, speed_bps, eta_sec, files_done, total_files)
        finished_ok(CopyResult)
        error_signal(str)
    """
    progress = Signal(int, int, str, float, float, int, int)
    finished_ok = Signal(object)  # CopyResult
    error_signal = Signal(str)

    def __init__(
        self,
        entries: List[FileEntry],
        dest_dir: str,
        flat_copy: bool = False,
        root_remap: str = '',
        original_drive: str = '',
        dedup_same_name_size: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.entries = entries
        self.dest_dir = os.path.abspath(dest_dir)
        self.flat_copy = flat_copy
        self.root_remap = root_remap
        self.original_drive = original_drive
        self.dedup_same_name_size = dedup_same_name_size
        self._cancelled = False
        self._default_conflict_action = ConflictAction.SKIP

    def set_conflict_action(self, action: ConflictAction, for_all: bool = True):
        """Set the conflict resolution action."""
        self._default_conflict_action = action

    def cancel(self):
        """Request immediate thread cancellation."""
        self._cancelled = True

    def _get_actual_path(self, entry: FileEntry) -> str:
        """Resolve actual source path on disk with root remapping applied."""
        path = os.path.join(entry.folder, entry.name)
        if self.root_remap and self.original_drive:
            if path.upper().startswith(self.original_drive.upper()):
                path = self.root_remap + path[len(self.original_drive):]
        return path

    def _get_dest_path(self, entry: FileEntry) -> str:
        """Compute safe destination path (flat or structured) with sanitized names."""
        safe_filename = sanitize_windows_filename(entry.name)

        if self.flat_copy:
            return os.path.join(self.dest_dir, safe_filename)
        else:
            folder = entry.folder
            if self.original_drive and folder.upper().startswith(self.original_drive.upper()):
                relative = folder[len(self.original_drive):]
            else:
                relative = folder.lstrip('\\/')

            # Sanitize each segment of the relative directory structure
            parts = [sanitize_windows_filename(p) for p in re.split(r'[\\/]', relative) if p]
            return os.path.join(self.dest_dir, *parts, safe_filename)

    def _get_unique_name(self, dest_path: str) -> str:
        """Generate a non-colliding unique filename if destination already exists."""
        base, ext = os.path.splitext(dest_path)
        counter = 1
        new_path = dest_path
        while os.path.exists(new_path):
            new_path = f"{base} ({counter}){ext}"
            counter += 1
        return new_path

    def run(self):
        result = CopyResult()
        result.total = len(self.entries)
        result.total_bytes = sum(e.size_bytes for e in self.entries)

        # Track duplicates for flat copy (same safe name and same size)
        seen_flat: Set[Tuple[str, int]] = set()

        start_time = time.time()
        bytes_copied = 0

        for i, entry in enumerate(self.entries):
            if self._cancelled:
                result.cancelled = True
                break

            source = self._get_actual_path(entry)
            dest = self._get_dest_path(entry)
            file_size = entry.size_bytes

            # In flat copy mode: deduplicate files having identical name and size
            if self.flat_copy and self.dedup_same_name_size:
                flat_key = (os.path.basename(dest).lower(), file_size)
                if flat_key in seen_flat:
                    result.skipped += 1
                    bytes_copied += file_size
                    continue
                seen_flat.add(flat_key)

            # Check if destination file equals source file
            if os.path.exists(source) and os.path.abspath(source).lower() == os.path.abspath(dest).lower():
                result.errors.append((source, "Destination is identical to source file"))
                continue

            # Check if source directory contains destination or equals destination
            source_dir = os.path.dirname(source)
            if is_subpath(source_dir, self.dest_dir) and not self.flat_copy:
                # If destination is nested inside the source folder structure being copied
                if os.path.abspath(source_dir).lower() == os.path.abspath(self.dest_dir).lower():
                    result.errors.append((source, "Destination directory cannot be identical to source directory"))
                    continue

            # Check if source exists on disk
            if not os.path.exists(source):
                result.errors.append((source, "Source file not found on disk"))
                continue

            # Create destination folder
            try:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
            except OSError as err:
                result.errors.append((source, f"Cannot create destination directory: {err}"))
                continue

            # Handle existing destination conflicts
            if os.path.exists(dest):
                action = self._default_conflict_action
                if action == ConflictAction.SKIP:
                    result.skipped += 1
                    bytes_copied += file_size
                    continue
                elif action == ConflictAction.RENAME:
                    dest = self._get_unique_name(dest)
                # OVERWRITE continues and replaces file

            # Copy file in 1 MB chunks with byte progress & mid-file cancellation cleanup
            file_copied_bytes = 0
            copy_failed = False

            try:
                with open(source, 'rb') as f_src, open(dest, 'wb') as f_dst:
                    while True:
                        if self._cancelled:
                            copy_failed = True
                            break

                        chunk = f_src.read(CHUNK_SIZE)
                        if not chunk:
                            break

                        f_dst.write(chunk)
                        chunk_len = len(chunk)
                        file_copied_bytes += chunk_len
                        bytes_copied += chunk_len

                        # Emit progress
                        elapsed = time.time() - start_time
                        speed = bytes_copied / elapsed if elapsed > 0 else 0.0
                        rem_bytes = max(0, result.total_bytes - bytes_copied)
                        eta = (rem_bytes / speed) if speed > 0 else 0.0

                        self.progress.emit(
                            bytes_copied,
                            result.total_bytes,
                            entry.name,
                            speed,
                            eta,
                            i + 1,
                            result.total
                        )

                if self._cancelled or copy_failed:
                    # Remove incomplete destination file so no corrupted files remain
                    try:
                        if os.path.exists(dest):
                            os.remove(dest)
                    except OSError:
                        pass
                    result.cancelled = True
                    break

                # Preserve file timestamps / attributes
                try:
                    shutil.copystat(source, dest)
                except OSError:
                    pass

                result.copied += 1
                result.copied_bytes += file_copied_bytes

            except Exception as exc:
                # Cleanup incomplete file on error
                try:
                    if os.path.exists(dest):
                        os.remove(dest)
                except OSError:
                    pass
                result.errors.append((source, str(exc)))

        self.finished_ok.emit(result)
