"""
Main Application Window for Drive Content Browser.
Assembles the complete virtualized UI:
- Folder tree hierarchy
- Filter bar (search, type, ext, size, date, sort)
- Grid view with lazy thumbnail loading
- Detailed list view
- Zoomable image/video preview panel
- Duplicate detection panel
- Background parser and availability checker
- Drive remapping & copy service integration
- Persistent settings & themes (Dark/Light)
"""
from __future__ import annotations

import os
import sys
from typing import Optional, List

from PySide6.QtCore import Qt, QSize, Slot, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QStackedWidget, QDockWidget, QMenuBar, QMenu, QToolBar,
    QStatusBar, QLabel, QProgressBar, QSlider, QPushButton,
    QFileDialog, QMessageBox, QApplication
)
from PySide6.QtGui import QAction, QIcon, QKeySequence

from core.settings import AppSettings
from core.data_store import DataStore
from core.parser import ParserThread, ParseResult
from services.thumbnail_service import ThumbnailService
from services.availability_service import AvailabilityService
from ui.file_grid_model import FileTableModel
from ui.file_grid_view import FileGridView
from ui.file_list_view import FileListView
from ui.folder_tree import FolderTreePanel
from ui.filter_bar import FilterBar
from ui.preview_panel import PreviewPanel
from ui.duplicate_panel import DuplicatePanel
from ui.copy_dialog import CopyDialog
from ui.settings_dialog import SettingsDialog
from ui.theme import apply_theme


class MainWindow(QMainWindow):
    """
    Main application window orchestrating all components.
    """

    def __init__(self, settings: Optional[AppSettings] = None, initial_file: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Drive Content Browser")
        self.setMinimumSize(1024, 680)

        self._settings = settings or AppSettings()
        self._data_store = DataStore()
        self._data_store.set_root_remap(self._settings.root_remap)

        # Services
        self._thumb_service = ThumbnailService(
            thumbnail_size=self._settings.thumbnail_size,
            max_cache_mb=self._settings.cache_size_mb,
            parent=self
        )
        self._avail_service = AvailabilityService(parent=self)
        self._avail_service.progress.connect(self._on_avail_progress)
        self._avail_service.finished.connect(self._on_avail_finished)

        # Model
        self._model = FileTableModel(self._data_store, parent=self)

        # Background parser
        self._parser_thread: Optional[ParserThread] = None

        # Filter state
        self._current_folder_filter: str = ""
        self._include_subfolders: bool = False

        self._setup_ui()
        self._setup_docks()
        self._setup_menus_and_toolbars()
        self._setup_status_bar()

        # Restore window state
        geom = self._settings.load_window_geometry()
        state = self._settings.load_window_state()
        if geom:
            self.restoreGeometry(geom)
        if state:
            self.restoreState(state)

        # Load initial file if provided
        if initial_file and os.path.isfile(initial_file):
            QTimer.singleShot(100, lambda: self._start_parsing_file(initial_file))

    def _setup_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # ─── Filter bar on top ───
        self._filter_bar = FilterBar(self)
        self._filter_bar.filters_changed.connect(self._apply_filters)
        main_layout.addWidget(self._filter_bar)

        # ─── Main horizontal splitter (Tree | Content) ───
        self._main_splitter = QSplitter(Qt.Horizontal, self)

        # Left: Folder tree
        self._folder_tree = FolderTreePanel(self)
        self._folder_tree.folder_selected.connect(self._on_folder_selected)
        self._folder_tree.show_all_requested.connect(self._on_show_all_folders)
        self._main_splitter.addWidget(self._folder_tree)

        # Center: Views (Grid or List)
        self._views_stack = QStackedWidget(self)

        self._grid_view = FileGridView(self._thumb_service, cell_size=self._settings.thumbnail_size, parent=self)
        self._grid_view.set_model(self._model)
        self._grid_view.entry_selected.connect(self._on_entry_selected)
        self._grid_view.entry_double_clicked.connect(self._on_entry_double_clicked)
        self._grid_view.selection_changed.connect(self._on_selection_changed)
        self._grid_view.copy_requested.connect(self._open_copy_dialog_with_indices)
        self._views_stack.addWidget(self._grid_view)

        self._list_view = FileListView(self)
        self._list_view.set_model(self._model)
        self._list_view.entry_selected.connect(self._on_entry_selected)
        self._list_view.entry_double_clicked.connect(self._on_entry_double_clicked)
        self._list_view.selection_changed.connect(self._on_selection_changed)
        self._list_view.copy_requested.connect(self._open_copy_dialog_with_indices)
        self._views_stack.addWidget(self._list_view)

        self._main_splitter.addWidget(self._views_stack)
        self._main_splitter.setStretchFactor(0, 1)
        self._main_splitter.setStretchFactor(1, 4)

        main_layout.addWidget(self._main_splitter, 1)

    def _setup_docks(self):
        # ─── Preview Dock ───
        self._preview_dock = QDockWidget("Preview", self)
        self._preview_dock.setObjectName("PreviewDock")
        self._preview_panel = PreviewPanel(self._data_store, self)
        self._preview_panel.navigate_requested.connect(self._on_preview_navigate)
        self._preview_panel.close_requested.connect(self._preview_dock.close)
        self._preview_dock.setWidget(self._preview_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self._preview_dock)

        # ─── Duplicate Dock ───
        self._duplicate_dock = QDockWidget("Duplicates", self)
        self._duplicate_dock.setObjectName("DuplicateDock")
        self._duplicate_panel = DuplicatePanel(self._data_store, self)
        self._duplicate_panel.file_selected.connect(self._on_entry_selected)
        self._duplicate_panel.copy_requested.connect(self._open_copy_dialog_with_indices)
        self._duplicate_dock.setWidget(self._duplicate_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self._duplicate_dock)
        self.tabifyDockWidget(self._preview_dock, self._duplicate_dock)
        self._preview_dock.raise_()

    def _setup_menus_and_toolbars(self):
        menu_bar = self.menuBar()

        # ─── File Menu ───
        file_menu = menu_bar.addMenu("&File")

        open_act = QAction("&Open Analyzer Export (.txt)...", self)
        open_act.setShortcut(QKeySequence.Open)
        open_act.triggered.connect(self._browse_and_open_file)
        file_menu.addAction(open_act)

        self._recent_menu = file_menu.addMenu("Open &Recent")
        self._update_recent_menu()

        file_menu.addSeparator()

        settings_act = QAction("&Settings...", self)
        settings_act.triggered.connect(self._open_settings_dialog)
        file_menu.addAction(settings_act)

        file_menu.addSeparator()

        exit_act = QAction("E&xit", self)
        exit_act.setShortcut(QKeySequence.Quit)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        # ─── Edit Menu ───
        edit_menu = menu_bar.addMenu("&Edit")

        select_all_act = QAction("Select &All", self)
        select_all_act.setShortcut(QKeySequence.SelectAll)
        select_all_act.triggered.connect(self._select_all_current_view)
        edit_menu.addAction(select_all_act)

        copy_paths_act = QAction("&Copy Path(s)", self)
        copy_paths_act.setShortcut(QKeySequence("Ctrl+Shift+C"))
        copy_paths_act.triggered.connect(self._copy_selected_paths)
        edit_menu.addAction(copy_paths_act)

        copy_files_act = QAction("&Copy Selected Files...", self)
        copy_files_act.setShortcut(QKeySequence("Ctrl+C"))
        copy_files_act.triggered.connect(self._open_copy_dialog_from_selection)
        edit_menu.addAction(copy_files_act)

        # ─── View Menu ───
        view_menu = menu_bar.addMenu("&View")

        grid_view_act = QAction("&Grid View", self)
        grid_view_act.setShortcut(QKeySequence("Ctrl+1"))
        grid_view_act.triggered.connect(lambda: self._set_view_mode(0))
        view_menu.addAction(grid_view_act)

        list_view_act = QAction("&List View", self)
        list_view_act.setShortcut(QKeySequence("Ctrl+2"))
        list_view_act.triggered.connect(lambda: self._set_view_mode(1))
        view_menu.addAction(list_view_act)

        view_menu.addSeparator()

        toggle_preview_act = self._preview_dock.toggleViewAction()
        toggle_preview_act.setText("Preview Panel")
        toggle_preview_act.setShortcut(QKeySequence("Ctrl+P"))
        view_menu.addAction(toggle_preview_act)

        toggle_dupe_act = self._duplicate_dock.toggleViewAction()
        toggle_dupe_act.setText("Duplicates Panel")
        toggle_dupe_act.setShortcut(QKeySequence("Ctrl+D"))
        view_menu.addAction(toggle_dupe_act)

        view_menu.addSeparator()

        toggle_theme_act = QAction("Toggle &Dark/Light Theme", self)
        toggle_theme_act.setShortcut(QKeySequence("Ctrl+T"))
        toggle_theme_act.triggered.connect(self._toggle_theme)
        view_menu.addAction(toggle_theme_act)

        # ─── Tools Menu ───
        tools_menu = menu_bar.addMenu("&Tools")

        check_avail_act = QAction("&Check File Availability", self)
        check_avail_act.setShortcut(QKeySequence("F5"))
        check_avail_act.triggered.connect(self._start_availability_check)
        tools_menu.addAction(check_avail_act)

        clear_cache_act = QAction("Clear &Thumbnail Cache", self)
        clear_cache_act.triggered.connect(self._clear_thumbnail_cache)
        tools_menu.addAction(clear_cache_act)

        # ─── Main ToolBar ───
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(toolbar)

        toolbar.addAction(open_act)
        toolbar.addSeparator()

        self._grid_btn = QPushButton("▦ Grid")
        self._grid_btn.setCheckable(True)
        self._grid_btn.setChecked(True)
        self._grid_btn.clicked.connect(lambda: self._set_view_mode(0))
        toolbar.addWidget(self._grid_btn)

        self._list_btn = QPushButton("☰ List")
        self._list_btn.setCheckable(True)
        self._list_btn.clicked.connect(lambda: self._set_view_mode(1))
        toolbar.addWidget(self._list_btn)

        toolbar.addSeparator()

        toolbar.addWidget(QLabel(" Size: "))
        self._zoom_slider = QSlider(Qt.Horizontal)
        self._zoom_slider.setRange(80, 320)
        self._zoom_slider.setValue(self._settings.thumbnail_size)
        self._zoom_slider.setMaximumWidth(120)
        self._zoom_slider.valueChanged.connect(self._on_zoom_changed)
        toolbar.addWidget(self._zoom_slider)

        toolbar.addSeparator()

        copy_btn = QPushButton("📋 Copy Selected")
        copy_btn.clicked.connect(self._open_copy_dialog_from_selection)
        toolbar.addWidget(copy_btn)

        avail_btn = QPushButton("🔍 Check Availability")
        avail_btn.clicked.connect(self._start_availability_check)
        toolbar.addWidget(avail_btn)

        toolbar.addSeparator()

        theme_btn = QPushButton("🌓 Theme")
        theme_btn.clicked.connect(self._toggle_theme)
        toolbar.addWidget(theme_btn)

    def _setup_status_bar(self):
        status_bar = self.statusBar()

        self._status_progress = QProgressBar()
        self._status_progress.setMaximumWidth(160)
        self._status_progress.setVisible(False)
        status_bar.addPermanentWidget(self._status_progress)

        self._status_files_label = QLabel("No file loaded")
        self._status_files_label.setStyleSheet("padding: 0 8px;")
        status_bar.addWidget(self._status_files_label, 1)

        self._status_avail_label = QLabel("")
        self._status_avail_label.setStyleSheet("padding: 0 8px; color: #88c0d0;")
        status_bar.addPermanentWidget(self._status_avail_label)

        self._status_cache_label = QLabel("")
        self._status_cache_label.setStyleSheet("padding: 0 8px; color: #888;")
        status_bar.addPermanentWidget(self._status_cache_label)

        self._status_remap_label = QLabel("")
        self._status_remap_label.setStyleSheet("padding: 0 8px; color: #e94560;")
        status_bar.addPermanentWidget(self._status_remap_label)
        self._update_remap_status_label()

    def _update_remap_status_label(self):
        if self._data_store.root_remap:
            orig = self._data_store.original_drive or "Drive"
            self._status_remap_label.setText(f"⮂ Remapped: {orig} ➜ {self._data_store.root_remap}")
        else:
            self._status_remap_label.setText("")

    def _update_recent_menu(self):
        self._recent_menu.clear()
        recent = self._settings.recent_files
        if not recent:
            no_act = self._recent_menu.addAction("No recent files")
            no_act.setEnabled(False)
            return

        for path in recent:
            act = self._recent_menu.addAction(path)
            act.triggered.connect(lambda checked=False, p=path: self._start_parsing_file(p))

        self._recent_menu.addSeparator()
        clear_act = self._recent_menu.addAction("Clear Recent List")
        clear_act.triggered.connect(self._settings.clear_recent_files)
        clear_act.triggered.connect(self._update_recent_menu)

    # ─── File Loading ───

    def _browse_and_open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Drive Analyzer Export File",
            "",
            "Text Files (*.txt);;All Files (*.*)"
        )
        if path:
            self._start_parsing_file(path)

    def _start_parsing_file(self, file_path: str):
        if not os.path.isfile(file_path):
            QMessageBox.warning(self, "Error", f"File not found: {file_path}")
            return

        if self._parser_thread and self._parser_thread.isRunning():
            self._parser_thread.cancel()
            self._parser_thread.wait()

        self._status_progress.setVisible(True)
        self._status_progress.setValue(0)
        self._status_files_label.setText(f"Loading {os.path.basename(file_path)}...")

        self._parser_thread = ParserThread(file_path, self)
        self._parser_thread.progress.connect(self._on_parse_progress)
        self._parser_thread.finished_ok.connect(lambda res: self._on_parse_finished(res, file_path))
        self._parser_thread.failed.connect(self._on_parse_failed)
        self._parser_thread.start()

    def _on_parse_progress(self, current: int, total: int):
        if total > 0:
            self._status_progress.setValue(int(current / total * 100))

    def _on_parse_finished(self, result: ParseResult, file_path: str):
        self._status_progress.setVisible(False)
        self._settings.add_recent_file(file_path)
        self._update_recent_menu()

        # Load into store
        self._data_store.load_result(result, file_path, self._settings.root_remap)
        self._update_remap_status_label()

        # Populate UI
        self._folder_tree.load_tree(self._data_store.roots)
        self._filter_bar.set_extensions(self._data_store.extensions)
        self._duplicate_panel.load_duplicates()

        # Refresh items
        self._current_folder_filter = ""
        self._include_subfolders = False
        self._apply_filters()

        # Automatically start availability check in background
        self._start_availability_check()

    def _on_parse_failed(self, error_msg: str):
        self._status_progress.setVisible(False)
        self._status_files_label.setText("Error loading file.")
        QMessageBox.critical(self, "Load Error", error_msg)

    # ─── Filtering & Sorting ───

    def _on_folder_selected(self, folder_path: str, include_subfolders: bool):
        self._current_folder_filter = folder_path
        self._include_subfolders = include_subfolders
        self._apply_filters()

    def _on_show_all_folders(self):
        self._current_folder_filter = ""
        self._include_subfolders = False
        self._apply_filters()

    def _apply_filters(self):
        """Execute filtering and sorting on DataStore."""
        if not self._data_store.entries:
            return

        # 1. Base folder indices
        if self._current_folder_filter:
            base_indices = self._data_store.get_folder_file_indices(
                self._current_folder_filter,
                include_subfolders=self._include_subfolders
            )
        else:
            base_indices = None

        # 2. Filter indices
        filtered = self._data_store.filter_indices(
            base_indices=base_indices,
            search_query=self._filter_bar.search_text,
            selected_types=self._filter_bar.file_type,
            selected_extensions=self._filter_bar.extension_filter,
            min_size_kb=self._filter_bar.min_size_kb,
            max_size_kb=self._filter_bar.max_size_kb,
            min_date=self._filter_bar.min_date,
            max_date=self._filter_bar.max_date
        )

        # 3. Sort indices
        sorted_indices = self._data_store.sort_indices(
            filtered,
            sort_key=self._filter_bar.sort_key,
            reverse=self._filter_bar.sort_reverse
        )

        # 4. Update model
        self._model.set_indices(sorted_indices)

        # 5. Update status
        total_count = len(self._data_store.entries)
        showing_count = len(sorted_indices)
        total_kb = sum(self._data_store.entries[i].size_kb for i in sorted_indices)
        total_size_disp = self._format_kb(total_kb)

        self._status_files_label.setText(
            f"Showing {showing_count:,} of {total_count:,} files  |  {total_size_disp}"
        )
        self._status_cache_label.setText(f"Cache: {self._thumb_service.cache_info}")

    @staticmethod
    def _format_kb(kb: float) -> str:
        if kb < 1024.0:
            return f"{kb:,.1f} KB"
        elif kb < 1024.0 * 1024.0:
            return f"{kb / 1024.0:,.1f} MB"
        else:
            return f"{kb / (1024.0 * 1024.0):,.2f} GB"

    # ─── View Modes & Zoom ───

    def _set_view_mode(self, mode_idx: int):
        """0 for Grid View, 1 for List View."""
        self._views_stack.setCurrentIndex(mode_idx)
        self._grid_btn.setChecked(mode_idx == 0)
        self._list_btn.setChecked(mode_idx == 1)

    def _on_zoom_changed(self, size: int):
        self._settings.thumbnail_size = size
        self._grid_view.set_cell_size(size)

    # ─── Selection & Preview ───

    def _on_entry_selected(self, entry_index: int):
        if 0 <= entry_index < len(self._data_store.entries):
            entry = self._data_store.entries[entry_index]
            self._preview_panel.show_entry(entry)

    def _on_entry_double_clicked(self, entry_index: int):
        self._on_entry_selected(entry_index)
        self._preview_dock.setVisible(True)
        self._preview_dock.raise_()

    def _on_selection_changed(self, selected_indices: List[int]):
        count = len(selected_indices)
        if count > 0:
            self.statusBar().showMessage(f"Selected {count:,} file(s)", 2000)

    def _on_preview_navigate(self, delta: int):
        current_indices = self._model.current_indices
        if not current_indices or not self._preview_panel._current_entry:
            return

        curr_idx = self._preview_panel._current_entry.index
        try:
            row = current_indices.index(curr_idx)
            next_row = max(0, min(len(current_indices) - 1, row + delta))
            next_entry_idx = current_indices[next_row]
            self._on_entry_selected(next_entry_idx)
        except ValueError:
            pass

    def _select_all_current_view(self):
        if self._views_stack.currentIndex() == 0:
            self._grid_view.select_all()
        else:
            self._list_view.select_all()

    def _get_current_selected_indices(self) -> List[int]:
        if self._views_stack.currentIndex() == 0:
            return self._grid_view.get_selected_indices()
        return self._list_view.get_selected_indices()

    def _copy_selected_paths(self):
        selected = self._get_current_selected_indices()
        if not selected:
            return
        paths = [self._data_store.get_actual_path(self._data_store.entries[i]) for i in selected]
        QApplication.clipboard().setText("\n".join(paths))
        self.statusBar().showMessage(f"Copied {len(paths)} path(s) to clipboard", 2500)

    # ─── Copy Dialog ───

    def _open_copy_dialog_from_selection(self):
        selected = self._get_current_selected_indices()
        if not selected:
            QMessageBox.information(self, "No Selection", "Please select files to copy.")
            return
        self._open_copy_dialog_with_indices(selected)

    def _open_copy_dialog_with_indices(self, indices: List[int]):
        if not indices:
            return
        dialog = CopyDialog(self._data_store, indices, parent=self)
        dialog.exec()

    # ─── Availability Service ───

    def _start_availability_check(self):
        if not self._data_store.entries:
            return
        self._status_avail_label.setText("Checking availability...")
        self._avail_service.check_availability(self._data_store)

    def _on_avail_progress(self, current: int, total: int):
        self._status_avail_label.setText(f"Checking folders: {current}/{total}")

    def _on_avail_finished(self, avail_count: int, unavail_count: int):
        self._status_avail_label.setText(f"Available: {avail_count:,} | Missing: {unavail_count:,}")
        self._model.beginResetModel()
        self._model.endResetModel()

    # ─── Settings & Themes ───

    def _open_settings_dialog(self):
        current_cfg = {
            'root_remap': self._settings.root_remap,
            'cache_size_mb': self._settings.cache_size_mb,
            'thumbnail_size': self._settings.thumbnail_size,
            'theme': self._settings.theme,
            'slideshow_interval': self._settings.slideshow_interval,
        }
        dialog = SettingsDialog(current_cfg, self._data_store.original_drive, parent=self)
        if dialog.exec():
            new_cfg = dialog.settings
            self._settings.root_remap = new_cfg['root_remap']
            self._settings.cache_size_mb = new_cfg['cache_size_mb']
            self._settings.thumbnail_size = new_cfg['thumbnail_size']
            self._settings.theme = new_cfg['theme']
            self._settings.slideshow_interval = new_cfg['slideshow_interval']

            self._data_store.set_root_remap(self._settings.root_remap)
            self._update_remap_status_label()
            self._zoom_slider.setValue(self._settings.thumbnail_size)
            apply_theme(QApplication.instance(), self._settings.theme == "dark")

    def _toggle_theme(self):
        current = self._settings.theme
        new_theme = "light" if current == "dark" else "dark"
        self._settings.theme = new_theme
        apply_theme(QApplication.instance(), new_theme == "dark")

    def _clear_thumbnail_cache(self):
        self._thumb_service.clear_cache()
        self._status_cache_label.setText(f"Cache: {self._thumb_service.cache_info}")
        self._grid_view.reset()
        self.statusBar().showMessage("Thumbnail cache cleared.", 2000)

    # ─── Window Lifecycle ───

    def closeEvent(self, event):
        # Save geometry and state
        self._settings.save_window_state(self.saveGeometry().data(), self.saveState().data())

        if self._parser_thread and self._parser_thread.isRunning():
            self._parser_thread.cancel()
            self._parser_thread.wait()

        self._avail_service.cancel()
        self._thumb_service.clear_cache()

        event.accept()
