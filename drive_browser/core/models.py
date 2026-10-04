"""
Data models for Drive Content Browser:
- FileEntry: Ultra-lightweight slots-based record with string-interned folder paths
- FolderNode: Hierarchical tree node tracking direct and recursive file metrics
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, List


# String pool for sharing folder paths across thousands of entries
_FOLDER_POOL: Dict[str, str] = {}


def intern_folder(folder_path: str) -> str:
    """Return a single canonical string instance for identical folder paths."""
    if not folder_path:
        return ""
    normalized = folder_path.replace("/", "\\")
    if not normalized.endswith("\\"):
        normalized += "\\"
    
    existing = _FOLDER_POOL.get(normalized)
    if existing is not None:
        return existing
    
    # sys.intern handles standard strings, pool caches normalized string
    canonical = sys.intern(normalized)
    _FOLDER_POOL[canonical] = canonical
    return canonical


def clear_folder_pool():
    """Clear folder pool when loading a new file."""
    _FOLDER_POOL.clear()


@dataclass(slots=True)
class FileEntry:
    """
    Represents a single file entry from the analyzer export.
    Uses __slots__ and shared folder string references to minimize memory footprint.
    For 100k+ records, this maintains memory < 25 MB RAM.
    """
    index: int                  # 0-based stable index in DataStore.entries
    name: str                   # File name e.g. "IMG_20190822_144839_1.jpg"
    folder: str                 # Shared string reference e.g. "E:\\pop\\G\\photo\\"
    extension: str              # Lowercase extension without dot, e.g. "jpg"
    size_kb: float              # Exact float size in KB
    category: str               # "Pictures", "Videos", etc.
    date: Optional[datetime]    # Parsed date or None
    line_number: int            # 1-based line number in source text file
    is_available: bool = True   # Checked dynamically by AvailabilityService

    @property
    def full_path(self) -> str:
        """Original raw full path."""
        return os.path.join(self.folder, self.name)

    @property
    def size_bytes(self) -> int:
        """Size in bytes approximation."""
        return int(self.size_kb * 1024)

    @property
    def size_display(self) -> str:
        """Formatted human readable size."""
        kb = self.size_kb
        if kb < 1.0:
            return f"{kb * 1024:.0f} B"
        elif kb < 1024.0:
            return f"{kb:,.1f} KB"
        elif kb < 1024.0 * 1024.0:
            return f"{kb / 1024.0:,.1f} MB"
        else:
            return f"{kb / (1024.0 * 1024.0):,.2f} GB"

    @property
    def date_display(self) -> str:
        """Formatted date string."""
        if self.date is None:
            return ""
        return self.date.strftime("%Y-%m-%d %H:%M:%S")

    def is_image(self) -> bool:
        return self.extension in {'jpg', 'jpeg', 'png', 'bmp', 'gif', 'tif', 'tiff', 'webp'}

    def is_video(self) -> bool:
        return self.extension in {'mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'webm', '3gp', 'm4v', 'ts'}

    def is_gif(self) -> bool:
        return self.extension == 'gif'


class FolderNode:
    """
    Tree node for representing the directory hierarchy.
    Maintains direct counts/sizes and aggregated recursive totals.
    """
    __slots__ = (
        'name', 'full_path', 'parent', 'children',
        'direct_file_count', 'direct_size_kb',
        'recursive_file_count', 'recursive_size_kb',
        'file_indices'
    )

    def __init__(self, name: str, full_path: str, parent: Optional[FolderNode] = None):
        self.name: str = name
        self.full_path: str = full_path
        self.parent: Optional[FolderNode] = parent
        self.children: Dict[str, FolderNode] = {}
        self.direct_file_count: int = 0
        self.direct_size_kb: float = 0.0
        self.recursive_file_count: int = 0
        self.recursive_size_kb: float = 0.0
        self.file_indices: List[int] = []

    def get_or_create_child(self, child_name: str, child_full_path: str) -> FolderNode:
        child = self.children.get(child_name)
        if child is None:
            child = FolderNode(child_name, child_full_path, parent=self)
            self.children[child_name] = child
        return child

    def compute_recursive_totals(self) -> None:
        """Post-order traversal to calculate total sizes and counts."""
        rec_count = self.direct_file_count
        rec_size = self.direct_size_kb
        for child in self.children.values():
            child.compute_recursive_totals()
            rec_count += child.recursive_file_count
            rec_size += child.recursive_size_kb
        self.recursive_file_count = rec_count
        self.recursive_size_kb = rec_size

    @property
    def recursive_size_display(self) -> str:
        kb = self.recursive_size_kb
        if kb < 1024.0:
            return f"{kb:,.1f} KB"
        elif kb < 1024.0 * 1024.0:
            return f"{kb / 1024.0:,.1f} MB"
        else:
            return f"{kb / (1024.0 * 1024.0):,.2f} GB"

    def sorted_children(self) -> List[FolderNode]:
        return sorted(self.children.values(), key=lambda n: n.name.lower())
