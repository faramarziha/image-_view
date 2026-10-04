"""
File model: QAbstractTableModel for virtualized file display.
Supports both list (table) and grid (icon) views.
Uses indices into the DataStore for memory efficiency.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QSize, Signal,
)
from PySide6.QtGui import QPixmap, QColor, QIcon

from core.data_store import DataStore
from core.models import FileEntry


# Column definitions for table view
COLUMNS = ['Name', 'Size', 'Date', 'Type', 'Path']
COL_NAME = 0
COL_SIZE = 1
COL_DATE = 2
COL_TYPE = 3
COL_PATH = 4


class FileTableModel(QAbstractTableModel):
    """
    Virtualized table model backed by a list of entry indices.
    Efficiently handles 100K+ rows without creating widgets for each.
    """

    def __init__(self, data_store: DataStore, parent=None):
        super().__init__(parent)
        self._store = data_store
        self._indices: list[int] = []  # Indices into data_store.entries
        self._sort_key = 'name'
        self._sort_reverse = False

    @property
    def current_indices(self) -> list[int]:
        return self._indices

    def set_indices(self, indices: list[int]) -> None:
        """Replace the displayed entries."""
        self.beginResetModel()
        self._indices = indices
        self.endResetModel()

    def get_entry(self, row: int) -> Optional[FileEntry]:
        """Get the FileEntry for a given row."""
        if 0 <= row < len(self._indices):
            idx = self._indices[row]
            return self._store.entries[idx]
        return None

    def get_entry_index(self, row: int) -> int:
        """Get the data store index for a given row."""
        if 0 <= row < len(self._indices):
            return self._indices[row]
        return -1

    # ── QAbstractTableModel interface ──

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._indices)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNS)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()

        if row < 0 or row >= len(self._indices):
            return None

        entry = self._store.entries[self._indices[row]]

        if role == Qt.DisplayRole:
            if col == COL_NAME:
                return entry.name
            elif col == COL_SIZE:
                return entry.size_display
            elif col == COL_DATE:
                return entry.date_display
            elif col == COL_TYPE:
                return entry.extension.upper()
            elif col == COL_PATH:
                return entry.folder

        elif role == Qt.ToolTipRole:
            return (f"Name: {entry.name}\n"
                    f"Path: {entry.folder}\n"
                    f"Size: {entry.size_display}\n"
                    f"Date: {entry.date_display}\n"
                    f"Type: {entry.extension.upper()}")

        elif role == Qt.TextAlignmentRole:
            if col == COL_SIZE:
                return int(Qt.AlignRight | Qt.AlignVCenter)
            elif col == COL_DATE:
                return int(Qt.AlignCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)

        elif role == Qt.UserRole:
            # Return the full file path for thumbnail requests
            return self._store.get_file_full_path(entry)

        elif role == Qt.UserRole + 1:
            # Return entry index in data store
            return self._indices[row]

        elif role == Qt.UserRole + 2:
            # Return the FileEntry itself
            return entry

        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            if 0 <= section < len(COLUMNS):
                return COLUMNS[section]
        return None

    def sort(self, column: int, order=Qt.AscendingOrder):
        """Sort by column. Uses DataStore's sort for efficiency."""
        key_map = {
            COL_NAME: 'name',
            COL_SIZE: 'size',
            COL_DATE: 'date',
            COL_TYPE: 'extension',
            COL_PATH: 'path',
        }
        key = key_map.get(column, 'name')
        reverse = (order == Qt.DescendingOrder)

        self.beginResetModel()
        self._indices = self._store.sort_indices(self._indices, key=key, reverse=reverse)
        self._sort_key = key
        self._sort_reverse = reverse
        self.endResetModel()

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable
