"""
Duplicate files panel: groups files by (name, size) and shows all copies.
Allows selecting all copies except one for marking/copying.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QComboBox,
)

from core.data_store import DataStore
from core.models import FileEntry


class DuplicatePanel(QWidget):
    """
    Shows duplicate file groups in a tree structure.
    Each group (name+size) is a parent, individual copies are children.
    """
    file_selected = Signal(int)       # entry index
    copy_requested = Signal(list)     # list of entry indices to copy

    def __init__(self, data_store: DataStore, parent=None):
        super().__init__(parent)
        self._store = data_store
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Header
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("🔄 Duplicate Files"))

        # Sort duplicates
        sort_label = QLabel("Sort:")
        header_layout.addWidget(sort_label)
        self._sort_combo = QComboBox()
        self._sort_combo.addItems(['Most copies', 'Largest first', 'Name'])
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        header_layout.addWidget(self._sort_combo)

        # Select all except one
        self._select_btn = QPushButton("Select all except first copy")
        self._select_btn.clicked.connect(self._select_all_except_first)
        header_layout.addWidget(self._select_btn)

        # Copy selected
        self._copy_btn = QPushButton("📋 Copy selected")
        self._copy_btn.clicked.connect(self._on_copy_selected)
        header_layout.addWidget(self._copy_btn)

        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Summary
        self._summary = QLabel("")
        self._summary.setStyleSheet("font-size: 11px; color: #888; padding: 2px 6px;")
        layout.addWidget(self._summary)

        # Tree widget
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(['Name / Path', 'Size', 'Date', 'Count'])
        self._tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._tree.header().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        layout.addWidget(self._tree)

    def load_duplicates(self):
        """Populate the tree with duplicate groups."""
        self._tree.clear()

        if not self._store.duplicates:
            self._summary.setText("No duplicate files found.")
            return

        total_groups = len(self._store.duplicates)
        total_dupes = sum(len(v) for v in self._store.duplicates.values())

        self._summary.setText(
            f"{total_groups:,} groups, {total_dupes:,} total files "
            f"({total_dupes - total_groups:,} duplicates)"
        )

        # Sort groups
        sort_idx = self._sort_combo.currentIndex()
        groups = list(self._store.duplicates.items())
        if sort_idx == 0:
            groups.sort(key=lambda x: len(x[1]), reverse=True)
        elif sort_idx == 1:
            groups.sort(key=lambda x: x[0][1], reverse=True)
        else:
            groups.sort(key=lambda x: x[0][0].lower())

        # Populate tree (limit to first 2000 groups for performance)
        for (name, size_kb), indices in groups[:2000]:
            entry0 = self._store.entries[indices[0]]
            group_item = QTreeWidgetItem([
                f"📄 {name}",
                entry0.size_display,
                '',
                f"{len(indices)} copies",
            ])
            group_item.setData(0, Qt.UserRole, indices)

            for idx in indices:
                entry = self._store.entries[idx]
                child = QTreeWidgetItem([
                    f"   📁 {entry.folder}",
                    entry.size_display,
                    entry.date_display,
                    '',
                ])
                child.setData(0, Qt.UserRole, idx)
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(0, Qt.Unchecked)
                group_item.addChild(child)

            self._tree.addTopLevelItem(group_item)

        if total_groups > 2000:
            info = QTreeWidgetItem([f"... and {total_groups - 2000} more groups", '', '', ''])
            self._tree.addTopLevelItem(info)

    def _on_sort_changed(self):
        self.load_duplicates()

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.UserRole)
        if isinstance(data, int):
            self.file_selected.emit(data)

    def _select_all_except_first(self):
        """Check all copies except the first one in each group."""
        for i in range(self._tree.topLevelItemCount()):
            group = self._tree.topLevelItem(i)
            for j in range(group.childCount()):
                child = group.child(j)
                if j == 0:
                    child.setCheckState(0, Qt.Unchecked)
                else:
                    child.setCheckState(0, Qt.Checked)

    def _on_copy_selected(self):
        """Collect all checked items and emit copy request."""
        selected_indices = []
        for i in range(self._tree.topLevelItemCount()):
            group = self._tree.topLevelItem(i)
            for j in range(group.childCount()):
                child = group.child(j)
                if child.checkState(0) == Qt.Checked:
                    idx = child.data(0, Qt.UserRole)
                    if isinstance(idx, int):
                        selected_indices.append(idx)

        if selected_indices:
            self.copy_requested.emit(selected_indices)

    def get_checked_indices(self) -> list[int]:
        """Get all currently checked entry indices."""
        result = []
        for i in range(self._tree.topLevelItemCount()):
            group = self._tree.topLevelItem(i)
            for j in range(group.childCount()):
                child = group.child(j)
                if child.checkState(0) == Qt.Checked:
                    idx = child.data(0, Qt.UserRole)
                    if isinstance(idx, int):
                        result.append(idx)
        return result
