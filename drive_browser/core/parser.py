"""
Parser for drive analyzer text files.
Robust BOM detection (UTF-16 LE/BE, UTF-8-BOM, UTF-8).
Processes tab-separated file records with error tolerance and progress tracking.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Callable, Optional, List, Tuple

from PySide6.QtCore import QThread, Signal

from core.models import FileEntry, intern_folder, clear_folder_pool


# ──────────────────── Encoding Detection ────────────────────

def detect_file_encoding(file_path: str) -> str:
    """
    Detect encoding using BOM signature or heuristic check.
    Supports UTF-16 (BOM stripped), UTF-8 BOM, standard UTF-8, and cp1256/cp1252 fallbacks.
    """
    with open(file_path, 'rb') as f:
        header = f.read(4)

    # Use 'utf-16' instead of 'utf-16-le' / 'utf-16-be' so Python automatically detects endianness and strips BOM
    if header.startswith(b'\xff\xfe') or header.startswith(b'\xfe\xff'):
        return 'utf-16'
    elif header.startswith(b'\xef\xbb\xbf'):
        return 'utf-8-sig'

    # Try reading first 64KB as UTF-8
    # Use incremental decoder so being cut off mid-character in the first 64KB does not raise UnicodeDecodeError
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(65536)
        import codecs
        decoder = codecs.getincrementaldecoder('utf-8')()
        decoder.decode(chunk, final=False)
        return 'utf-8'
    except UnicodeDecodeError:
        # Check if UTF-16 LE without BOM
        try:
            with open(file_path, 'r', encoding='utf-16-le') as f:
                f.read(65536)
            return 'utf-16-le'
        except UnicodeDecodeError:
            return 'cp1256'  # Persian / Arabic Windows fallback


# ──────────────────── Parsing Helpers ────────────────────

_SIZE_PATTERN = re.compile(r'^([\d,]+(?:\.\d+)?)\s*KB$', re.IGNORECASE)

_DATE_FORMATS = (
    "%m/%d/%Y %I:%M:%S %p",   # 8/22/2019 9:18:40 AM
    "%m/%d/%Y %H:%M:%S",       # 8/22/2019 14:18:40
    "%Y-%m-%d %H:%M:%S",       # 2019-08-22 14:18:40
    "%m/%d/%Y %I:%M %p",       # 8/22/2019 9:18 AM
)


def parse_size_to_kb(raw_size: str) -> Optional[float]:
    raw = raw_size.strip()
    match = _SIZE_PATTERN.match(raw)
    if not match:
        return None
    try:
        return float(match.group(1).replace(',', ''))
    except ValueError:
        return None


def parse_datetime(raw_date: str) -> Optional[datetime]:
    cleaned = raw_date.strip()
    if not cleaned:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def parse_single_line(line: str, line_number: int, entry_index: int) -> Optional[FileEntry]:
    """
    Parse a single tab-separated line into a FileEntry.
    Expected format: Name <TAB> Folder <TAB> Ext <TAB> Size <TAB> Category <TAB> Date <TAB>
    """
    line = line.rstrip('\r\n')
    if line.startswith('\ufeff'):
        line = line[1:]
    if not line.strip():
        return None

    parts = line.split('\t')
    if len(parts) < 6:
        return None

    name = parts[0].strip()
    folder_raw = parts[1].strip()
    ext = parts[2].strip().lower().lstrip('.')
    size_raw = parts[3].strip()
    category = parts[4].strip()
    date_raw = parts[5].strip()

    if not name or not folder_raw:
        return None

    size_kb = parse_size_to_kb(size_raw)
    if size_kb is None:
        return None

    dt = parse_datetime(date_raw)
    folder_interned = intern_folder(folder_raw)

    return FileEntry(
        index=entry_index,
        name=name,
        folder=folder_interned,
        extension=ext,
        size_kb=size_kb,
        category=category,
        date=dt,
        line_number=line_number,
        is_available=True
    )


# ──────────────────── Parser Output ────────────────────

class ParseResult:
    __slots__ = ('entries', 'skipped_lines', 'total_lines', 'encoding')

    def __init__(self):
        self.entries: List[FileEntry] = []
        self.skipped_lines: List[Tuple[int, str]] = []  # (line_number, snippet)
        self.total_lines: int = 0
        self.encoding: str = ""


def parse_analyzer_file(
    file_path: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    is_cancelled: Optional[Callable[[], bool]] = None
) -> ParseResult:
    """
    Parse the analyzer text file with progress reporting and cancellation support.
    """
    result = ParseResult()
    clear_folder_pool()

    encoding = detect_file_encoding(file_path)
    result.encoding = encoding

    # Count lines first or estimate from file size
    with open(file_path, 'r', encoding=encoding, errors='replace') as f:
        lines = f.readlines()

    result.total_lines = len(lines)
    entry_idx = 0
    report_step = max(500, result.total_lines // 100) if result.total_lines > 0 else 500

    for i, line in enumerate(lines):
        if is_cancelled and is_cancelled():
            break

        if i == 0 and line.startswith('\ufeff'):
            line = line[1:]

        line_num = i + 1
        entry = parse_single_line(line, line_num, entry_idx)
        if entry is not None:
            result.entries.append(entry)
            entry_idx += 1
        else:
            stripped = line.strip()
            if stripped:
                result.skipped_lines.append((line_num, stripped[:150]))

        if progress_cb and i % report_step == 0:
            progress_cb(i, result.total_lines)

    if progress_cb:
        progress_cb(result.total_lines, result.total_lines)

    return result


class ParserThread(QThread):
    """Worker thread for background parsing."""
    progress = Signal(int, int)       # current, total
    finished_ok = Signal(object)      # ParseResult
    failed = Signal(str)              # Error message

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self._cancelled = False

    def run(self):
        try:
            res = parse_analyzer_file(
                self.file_path,
                progress_cb=self._on_progress,
                is_cancelled=lambda: self._cancelled
            )
            if not self._cancelled:
                self.finished_ok.emit(res)
        except Exception as exc:
            self.failed.emit(f"Failed to read file: {exc}")

    def _on_progress(self, current: int, total: int):
        self.progress.emit(current, total)

    def cancel(self):
        self._cancelled = True
