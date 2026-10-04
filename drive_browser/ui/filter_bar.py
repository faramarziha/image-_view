"""
Filter bar: search, type filter, extension filter, size range, date range.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLineEdit, QComboBox,
    QPushButton, QLabel, QSpinBox, QDateEdit, QCheckBox,
    QGroupBox, QFrame, QSizePolicy,
)
from PySide6.QtGui import QIcon


class FilterBar(QWidget):
    """
    Compact filter bar with search, type filter, and expandable advanced filters.
    Emits filters_changed whenever any filter is modified.
    """
    filters_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self.filters_changed.emit)
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)

        # ─── Top row: Search + Quick filters ───
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Search files and folders (supports Persian)...")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_filter_changed)
        self._search.setMinimumWidth(250)
        top_row.addWidget(self._search, 2)

        # Type filter
        type_label = QLabel("Type:")
        top_row.addWidget(type_label)
        self._type_combo = QComboBox()
        self._type_combo.addItems(['All', 'Images', 'Videos', 'GIFs', 'Other'])
        self._type_combo.currentIndexChanged.connect(self._on_filter_changed)
        top_row.addWidget(self._type_combo)

        # Sort
        sort_label = QLabel("Sort:")
        top_row.addWidget(sort_label)
        self._sort_combo = QComboBox()
        self._sort_combo.addItems(['Name ↑', 'Name ↓', 'Size ↑', 'Size ↓',
                                    'Date ↑', 'Date ↓', 'Type ↑', 'Type ↓',
                                    'Path ↑', 'Path ↓'])
        self._sort_combo.currentIndexChanged.connect(self._on_filter_changed)
        top_row.addWidget(self._sort_combo)

        # Advanced toggle
        self._adv_btn = QPushButton("⚙ Filters")
        self._adv_btn.setCheckable(True)
        self._adv_btn.setMaximumWidth(100)
        self._adv_btn.toggled.connect(self._toggle_advanced)
        top_row.addWidget(self._adv_btn)

        main_layout.addLayout(top_row)

        # ─── Advanced filters (hidden by default) ───
        self._adv_frame = QFrame()
        self._adv_frame.setVisible(False)
        adv_layout = QHBoxLayout(self._adv_frame)
        adv_layout.setContentsMargins(0, 4, 0, 4)
        adv_layout.setSpacing(12)

        # Extension filter
        ext_label = QLabel("Extension:")
        adv_layout.addWidget(ext_label)
        self._ext_combo = QComboBox()
        self._ext_combo.addItem("All")
        self._ext_combo.setMinimumWidth(80)
        self._ext_combo.currentIndexChanged.connect(self._on_filter_changed)
        adv_layout.addWidget(self._ext_combo)

        # Size range
        size_label = QLabel("Size (KB):")
        adv_layout.addWidget(size_label)
        self._min_size = QSpinBox()
        self._min_size.setRange(0, 999999999)
        self._min_size.setSpecialValueText("Min")
        self._min_size.setSuffix(" KB")
        self._min_size.valueChanged.connect(self._on_filter_changed)
        adv_layout.addWidget(self._min_size)

        adv_layout.addWidget(QLabel("–"))

        self._max_size = QSpinBox()
        self._max_size.setRange(0, 999999999)
        self._max_size.setSpecialValueText("Max")
        self._max_size.setSuffix(" KB")
        self._max_size.valueChanged.connect(self._on_filter_changed)
        adv_layout.addWidget(self._max_size)

        # Date range
        date_label = QLabel("Date:")
        adv_layout.addWidget(date_label)

        self._date_filter_check = QCheckBox("Enable")
        self._date_filter_check.toggled.connect(self._on_filter_changed)
        adv_layout.addWidget(self._date_filter_check)

        self._min_date = QDateEdit()
        self._min_date.setCalendarPopup(True)
        self._min_date.setDisplayFormat("yyyy-MM-dd")
        self._min_date.setDate(datetime(2000, 1, 1).date() if hasattr(datetime(2000,1,1), 'date') else None)
        self._min_date.dateChanged.connect(self._on_filter_changed)
        self._min_date.setEnabled(False)
        adv_layout.addWidget(self._min_date)

        adv_layout.addWidget(QLabel("–"))

        self._max_date = QDateEdit()
        self._max_date.setCalendarPopup(True)
        self._max_date.setDisplayFormat("yyyy-MM-dd")
        self._max_date.setDate(datetime.now().date() if hasattr(datetime.now(), 'date') else None)
        self._max_date.dateChanged.connect(self._on_filter_changed)
        self._max_date.setEnabled(False)
        adv_layout.addWidget(self._max_date)

        # Reset button
        reset_btn = QPushButton("Reset")
        reset_btn.setMaximumWidth(70)
        reset_btn.clicked.connect(self.reset_filters)
        adv_layout.addWidget(reset_btn)

        adv_layout.addStretch()
        main_layout.addWidget(self._adv_frame)

    def _toggle_advanced(self, checked: bool):
        self._adv_frame.setVisible(checked)

    def _on_filter_changed(self):
        # Enable/disable date inputs
        date_enabled = self._date_filter_check.isChecked()
        self._min_date.setEnabled(date_enabled)
        self._max_date.setEnabled(date_enabled)

        # Debounce to avoid excessive updates
        self._debounce_timer.start()

    def set_extensions(self, extensions: list[str]):
        """Populate extension dropdown from loaded data."""
        self._ext_combo.clear()
        self._ext_combo.addItem("All")
        for ext in extensions:
            self._ext_combo.addItem(ext)

    # ─── Getters for current filter state ───

    @property
    def search_text(self) -> str:
        return self._search.text()

    @property
    def file_type(self) -> Optional[str]:
        type_map = {0: None, 1: 'image', 2: 'video', 3: 'gif', 4: 'other'}
        return type_map.get(self._type_combo.currentIndex())

    @property
    def extension_filter(self) -> Optional[set[str]]:
        if self._ext_combo.currentIndex() == 0:
            return None
        return {self._ext_combo.currentText()}

    @property
    def min_size_kb(self) -> Optional[float]:
        val = self._min_size.value()
        return val if val > 0 else None

    @property
    def max_size_kb(self) -> Optional[float]:
        val = self._max_size.value()
        return val if val > 0 else None

    @property
    def min_date(self) -> Optional[datetime]:
        if not self._date_filter_check.isChecked():
            return None
        qdate = self._min_date.date()
        return datetime(qdate.year(), qdate.month(), qdate.day())

    @property
    def max_date(self) -> Optional[datetime]:
        if not self._date_filter_check.isChecked():
            return None
        qdate = self._max_date.date()
        return datetime(qdate.year(), qdate.month(), qdate.day(), 23, 59, 59)

    @property
    def sort_key(self) -> str:
        keys = ['name', 'name', 'size', 'size', 'date', 'date',
                'extension', 'extension', 'path', 'path']
        idx = self._sort_combo.currentIndex()
        return keys[idx] if 0 <= idx < len(keys) else 'name'

    @property
    def sort_reverse(self) -> bool:
        return self._sort_combo.currentIndex() % 2 == 1

    def reset_filters(self):
        """Reset all filters to defaults."""
        self._search.clear()
        self._type_combo.setCurrentIndex(0)
        self._ext_combo.setCurrentIndex(0)
        self._min_size.setValue(0)
        self._max_size.setValue(0)
        self._date_filter_check.setChecked(False)
        self._sort_combo.setCurrentIndex(0)
