"""
File list view: Virtualized QTableView for browsing drive entries in detail tabular view.
Integrates sorting, multi-selection, context menus, and keyboard shortcuts.
"""
from __future__ import annotations

import os
import subprocess
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, QPoint, QModelIndex
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableView, QHeaderView, QMenu,
    QAbstractItemView, QApplication
)
from PySide6.QtGui import QAction, QKeySequence

from core.models import FileEntry
from ui.file_grid_model import (
    FileTableModel, COL_NAME, COL_SIZE, COL_DATE, COL_TYPE, COL_PATH
)


class FileListView(QWidget):
    """
    Detailed tabular list view for files.
    """
    entry_selected = Signal(int)           # DataStore entry index
    entry_double_clicked = Signal(int)     # DataStore entry index
    selection_changed = Signal(list)       # List of selected DataStore indices
    copy_requested = Signal(list)          # List of selected indices to copy

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model: Optional[FileTableModel] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._table = QTableView()
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setSortingEnabled(True)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setDefaultSectionSize(26)
        self._table.verticalHeader().setVisible(False)

        # Header configuration
        header = self._table.horizontalHeader()
        header.setSectionsMovable(True)
        header.setHighlightSections(False)
        header.setStretchLastSection(True)

        # Context menu & events
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.doubleClicked.connect(self._on_double_clicked)

        layout.addWidget(self._table)

    def set_model(self, model: FileTableModel):
        self._model = model
        self._table.setModel(model)

        if self._table.selectionModel():
            self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)

        # Setup column sizes
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(COL_NAME, QHeaderView.Interactive)
        header.resizeSection(COL_NAME, 300)
        header.setSectionResizeMode(COL_SIZE, QHeaderView.Interactive)
        header.resizeSection(COL_SIZE, 90)
        header.setSectionResizeMode(COL_DATE, QHeaderView.Interactive)
        header.resizeSection(COL_DATE, 150)
        header.setSectionResizeMode(COL_TYPE, QHeaderView.Interactive)
        header.resizeSection(COL_TYPE, 70)
        header.setSectionResizeMode(COL_PATH, QHeaderView.Stretch)

    def get_selected_indices(self) -> List[int]:
        """Return list of selected DataStore entry indices."""
        if not self._model or not self._table.selectionModel():
            return []
        selected_rows = {index.row() for index in self._table.selectionModel().selectedRows()}
        result = []
        for row in selected_rows:
            idx = self._model.get_entry_index(row)
            if idx != -1:
                result.append(idx)
        return result

    def select_all(self):
        self._table.selectAll()

    def clear_selection(self):
        self._table.clearSelection()

    def _on_selection_changed(self):
        selected = self.get_selected_indices()
        self.selection_changed.emit(selected)
        if selected:
            # Emit first selected for preview
            self.entry_selected.emit(selected[0])

    def _on_double_clicked(self, index: QModelIndex):
        if self._model and index.isValid():
            entry_idx = self._model.get_entry_index(index.row())
            if entry_idx != -1:
                self.entry_double_clicked.emit(entry_idx)

    def _show_context_menu(self, pos: QPoint):
        if not self._model:
            return

        selected_indices = self.get_selected_indices()
        menu = QMenu(self)

        if len(selected_indices) == 1:
            preview_act = menu.addAction("👁 Preview")
            preview_act.triggered.connect(lambda: self.entry_double_clicked.emit(selected_indices[0]))

            show_explorer_act = menu.addAction("📂 Show in Explorer")
            show_explorer_act.triggered.connect(lambda: self._open_in_explorer(selected_indices[0]))

            copy_path_act = menu.addAction("📋 Copy Path")
            copy_path_act.triggered.connect(lambda: self._copy_path_to_clipboard(selected_indices[0]))

            menu.addSeparator()

        if selected_indices:
            copy_files_act = menu.addAction(f"📦 Copy {len(selected_indices)} File(s)...")
            copy_files_act.triggered.connect(lambda: self.copy_requested.emit(selected_indices))
            menu.addSeparator()

        select_all_act = menu.addAction("Select All")
        select_all_act.setShortcut(QKeySequence.SelectAll)
        select_all_act.triggered.connect(self.select_all)

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _open_in_explorer(self, entry_index: int):
        if not self._model:
            return
        entry = self._model._store.entries[entry_index]
        actual_path = self._model._store.get_actual_path(entry)
        if os.path.isfile(actual_path):
            subprocess.run(['explorer', f'/select,{actual_path}'], check=False)
        else:
            folder = os.path.dirname(actual_path)
            if os.path.isdir(folder):
                os.startfile(folder)

    def _copy_path_to_clipboard(self, entry_index: int):
        if not self._model:
            return
        entry = self._model._store.entries[entry_index]
        actual_path = self._model._store.get_actual_path(entry)
        QApplication.clipboard().setText(actual_path)
