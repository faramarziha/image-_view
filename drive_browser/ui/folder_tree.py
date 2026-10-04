"""
Folder tree panel: QTreeView showing the folder hierarchy
built from the parsed file entries.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItemModel, QStandardItem, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeView, QCheckBox, QLabel, QHBoxLayout,
)

from core.models import FolderNode


class FolderTreePanel(QWidget):
    """
    Left panel showing the folder hierarchy as a tree.
    Emits folder_selected with the folder path and include_subfolders flag.
    """
    folder_selected = Signal(str, bool)  # (folder_path, include_subfolders)
    show_all_requested = Signal()         # Show all files (no folder filter)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Header
        header = QLabel("📁 Folders")
        header.setStyleSheet("font-weight: bold; font-size: 14px; padding: 6px;")
        layout.addWidget(header)

        # Include subfolders checkbox
        self._subfolder_check = QCheckBox("Include subfolders")
        self._subfolder_check.setChecked(False)
        self._subfolder_check.toggled.connect(self._on_subfolder_toggled)
        layout.addWidget(self._subfolder_check)

        # Tree view
        self._tree = QTreeView()
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(True)
        self._tree.setExpandsOnDoubleClick(True)
        self._tree.setIndentation(18)
        self._tree.clicked.connect(self._on_item_clicked)
        layout.addWidget(self._tree)

        # Summary label
        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet("font-size: 11px; padding: 4px; color: #888;")
        layout.addWidget(self._summary_label)

        # Model
        self._model = QStandardItemModel()
        self._tree.setModel(self._model)

        # Internal state
        self._folder_path_map: dict[int, str] = {}  # item id → folder path
        self._current_path: str = ''

    def load_tree(self, roots: dict[str, FolderNode]) -> None:
        """Build the tree model from folder roots."""
        self._model.clear()
        self._folder_path_map.clear()

        # Add "All Files" item at the top
        all_item = QStandardItem("📋 All Files")
        all_item.setEditable(False)
        self._folder_path_map[id(all_item)] = ''
        self._model.appendRow(all_item)

        total_folders = 0
        for drive_path, root_node in sorted(roots.items()):
            drive_item = self._create_folder_item(root_node)
            self._model.appendRow(drive_item)
            total_folders += self._count_nodes(root_node)

        self._summary_label.setText(f"{total_folders} folders")

        # Expand first level
        self._tree.expandToDepth(0)

    def _create_folder_item(self, node: FolderNode) -> QStandardItem:
        """Recursively create tree items for a folder node."""
        display = f"{node.name}  ({node.recursive_file_count} files, {node.recursive_size_display})"
        item = QStandardItem(display)
        item.setEditable(False)
        item.setToolTip(f"Path: {node.full_path}\n"
                        f"Direct: {node.direct_file_count} files\n"
                        f"Total: {node.recursive_file_count} files\n"
                        f"Size: {node.recursive_size_display}")

        self._folder_path_map[id(item)] = node.full_path

        # Add children sorted by name
        for child in node.sorted_children():
            child_item = self._create_folder_item(child)
            item.appendRow(child_item)

        return item

    def _count_nodes(self, node: FolderNode) -> int:
        count = 1
        for child in node.children.values():
            count += self._count_nodes(child)
        return count

    def _on_item_clicked(self, index):
        item = self._model.itemFromIndex(index)
        if item is None:
            return

        item_id = id(item)
        folder_path = self._folder_path_map.get(item_id, '')

        if folder_path == '':
            # "All Files" selected
            self.show_all_requested.emit()
        else:
            self._current_path = folder_path
            include_sub = self._subfolder_check.isChecked()
            self.folder_selected.emit(folder_path, include_sub)

    def _on_subfolder_toggled(self, checked: bool):
        """Re-emit with current folder when checkbox changes."""
        if self._current_path:
            self.folder_selected.emit(self._current_path, checked)
