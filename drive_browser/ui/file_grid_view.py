"""
File grid view: Virtualized QListView in IconMode for browsing thumbnails.
Integrates ThumbnailDelegate, dynamic resizing, out-of-view task cancellation,
context menus, and multi-selection.
"""
from __future__ import annotations

import os
import subprocess
from typing import List, Optional, Set

from PySide6.QtCore import Qt, Signal, QPoint, QModelIndex, QSize, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QListView, QMenu, QAbstractItemView, QApplication
)
from PySide6.QtGui import QKeySequence

from core.models import FileEntry
from services.thumbnail_service import ThumbnailService
from ui.file_grid_model import FileTableModel
from ui.delegates import ThumbnailDelegate


class FileGridView(QWidget):
    """
    Virtualized grid of thumbnails with smooth scrolling and dynamic loading.
    """
    entry_selected = Signal(int)           # DataStore entry index
    entry_double_clicked = Signal(int)     # DataStore entry index
    selection_changed = Signal(list)       # List of selected DataStore indices
    copy_requested = Signal(list)          # List of selected indices to copy

    def __init__(self, thumbnail_service: ThumbnailService, cell_size: int = 160, parent=None):
        super().__init__(parent)
        self._thumb_service = thumbnail_service
        self._cell_size = cell_size
        self._model: Optional[FileTableModel] = None

        # Debounce timer for out-of-view request pruning
        self._prune_timer = QTimer(self)
        self._prune_timer.setSingleShot(True)
        self._prune_timer.setInterval(150)
        self._prune_timer.timeout.connect(self._prune_out_of_view_requests)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._view = QListView()
        self._view.setViewMode(QListView.IconMode)
        self._view.setResizeMode(QListView.Adjust)
        self._view.setUniformItemSizes(True)
        self._view.setMovement(QListView.Static)
        self._view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._view.setSpacing(8)

        # Delegate
        self._delegate = ThumbnailDelegate(self._thumb_service, cell_size=self._cell_size, parent=self)
        self._view.setItemDelegate(self._delegate)
        self._update_grid_size()

        # Connect scroll pruning
        self._view.verticalScrollBar().valueChanged.connect(lambda: self._prune_timer.start())

        # Connect thumbnail ready to viewport redraw
        self._thumb_service.thumbnail_ready.connect(self._on_thumbnail_ready)

        # Context menu & clicks
        self._view.setContextMenuPolicy(Qt.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._show_context_menu)
        self._view.doubleClicked.connect(self._on_double_clicked)

        layout.addWidget(self._view)

    def set_model(self, model: FileTableModel):
        self._model = model
        self._view.setModel(model)

        if self._view.selectionModel():
            self._view.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def set_cell_size(self, size: int):
        self._cell_size = max(80, min(400, size))
        self._delegate.cell_size = self._cell_size
        self._update_grid_size()
        self._view.reset()  # Refresh layout with new sizes

    def _update_grid_size(self):
        self._view.setGridSize(QSize(self._cell_size + 12, self._cell_size + 36))

    def get_selected_indices(self) -> List[int]:
        if not self._model or not self._view.selectionModel():
            return []
        selected_indexes = self._view.selectionModel().selectedIndexes()
        result = []
        for index in selected_indexes:
            if index.column() == 0:
                idx = self._model.get_entry_index(index.row())
                if idx != -1:
                    result.append(idx)
        return result

    def select_all(self):
        self._view.selectAll()

    def clear_selection(self):
        self._view.clearSelection()

    def _on_selection_changed(self):
        selected = self.get_selected_indices()
        self.selection_changed.emit(selected)
        if selected:
            self.entry_selected.emit(selected[0])

    def _on_double_clicked(self, index: QModelIndex):
        if self._model and index.isValid():
            entry_idx = self._model.get_entry_index(index.row())
            if entry_idx != -1:
                self.entry_double_clicked.emit(entry_idx)

    def _on_thumbnail_ready(self, file_path: str, pixmap):
        """Redraw visible area when a thumbnail arrives."""
        self._view.viewport().update()

    def _prune_out_of_view_requests(self):
        """Cancel queued thumbnail tasks for items no longer inside viewport."""
        if not self._model:
            return

        viewport_rect = self._view.viewport().rect()
        top_left_idx = self._view.indexAt(viewport_rect.topLeft())
        bottom_right_idx = self._view.indexAt(viewport_rect.bottomRight())

        if not top_left_idx.isValid():
            return

        start_row = max(0, top_left_idx.row() - 20)
        end_row = bottom_right_idx.row() + 20 if bottom_right_idx.isValid() else self._model.rowCount()

        visible_paths: Set[str] = set()
        for row in range(start_row, min(end_row, self._model.rowCount())):
            entry = self._model.get_entry(row)
            if entry:
                visible_paths.add(self._model._store.get_actual_path(entry))

        if visible_paths:
            self._thumb_service.cancel_out_of_view(visible_paths)

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

        menu.exec(self._view.viewport().mapToGlobal(pos))

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
