"""
Settings dialog: root path remapping, cache size, thumbnail size, theme.
"""
from __future__ import annotations

import json
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QComboBox, QGroupBox, QCheckBox,
    QFormLayout, QFileDialog,
)


class SettingsDialog(QDialog):
    """
    Application settings dialog.
    """
    settings_changed = Signal(dict)

    DEFAULT_SETTINGS = {
        'root_remap': '',
        'cache_size_mb': 512,
        'thumbnail_size': 200,
        'theme': 'dark',
        'slideshow_interval': 3,
    }

    def __init__(self, current_settings: dict, original_drive: str = '', parent=None):
        super().__init__(parent)
        self._settings = dict(current_settings)
        self._original_drive = original_drive
        self.setWindowTitle("Settings")
        self.setMinimumWidth(450)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ─── Root Path Remapping ───
        remap_group = QGroupBox("Drive Path Remapping")
        remap_layout = QFormLayout(remap_group)

        remap_layout.addRow("Original drive:", QLabel(self._original_drive or "N/A"))

        remap_row = QHBoxLayout()
        self._remap_input = QLineEdit(self._settings.get('root_remap', ''))
        self._remap_input.setPlaceholderText("e.g. F:\\ or D:\\backup\\")
        remap_row.addWidget(self._remap_input)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse_remap)
        remap_row.addWidget(browse_btn)
        remap_layout.addRow("Remap to:", remap_row)

        layout.addWidget(remap_group)

        # ─── Display Settings ───
        display_group = QGroupBox("Display")
        display_layout = QFormLayout(display_group)

        self._thumb_size = QSpinBox()
        self._thumb_size.setRange(80, 400)
        self._thumb_size.setValue(self._settings.get('thumbnail_size', 200))
        self._thumb_size.setSuffix(" px")
        display_layout.addRow("Thumbnail size:", self._thumb_size)

        self._cache_size = QSpinBox()
        self._cache_size.setRange(64, 4096)
        self._cache_size.setValue(self._settings.get('cache_size_mb', 512))
        self._cache_size.setSuffix(" MB")
        display_layout.addRow("Thumbnail cache:", self._cache_size)

        self._theme_combo = QComboBox()
        self._theme_combo.addItems(['Dark', 'Light'])
        if self._settings.get('theme', 'dark') == 'light':
            self._theme_combo.setCurrentIndex(1)
        display_layout.addRow("Theme:", self._theme_combo)

        layout.addWidget(display_group)

        # ─── Slideshow ───
        slide_group = QGroupBox("Slideshow")
        slide_layout = QFormLayout(slide_group)

        self._slide_interval = QSpinBox()
        self._slide_interval.setRange(1, 60)
        self._slide_interval.setValue(self._settings.get('slideshow_interval', 3))
        self._slide_interval.setSuffix(" seconds")
        slide_layout.addRow("Interval:", self._slide_interval)

        layout.addWidget(slide_group)

        # ─── Buttons ───
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(save_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _browse_remap(self):
        path = QFileDialog.getExistingDirectory(self, "Select Root Path")
        if path:
            # Normalize to Windows path with trailing backslash
            path = path.replace('/', '\\')
            if not path.endswith('\\'):
                path += '\\'
            self._remap_input.setText(path)

    def _save(self):
        self._settings = {
            'root_remap': self._remap_input.text().strip(),
            'cache_size_mb': self._cache_size.value(),
            'thumbnail_size': self._thumb_size.value(),
            'theme': 'dark' if self._theme_combo.currentIndex() == 0 else 'light',
            'slideshow_interval': self._slide_interval.value(),
        }
        self.settings_changed.emit(self._settings)
        self.accept()

    @property
    def settings(self) -> dict:
        return dict(self._settings)

    # ─── Persistent settings ───

    @staticmethod
    def _settings_path() -> str:
        app_data = os.path.join(os.path.expanduser('~'), '.drive_browser')
        os.makedirs(app_data, exist_ok=True)
        return os.path.join(app_data, 'settings.json')

    @staticmethod
    def load_settings() -> dict:
        path = SettingsDialog._settings_path()
        settings = dict(SettingsDialog.DEFAULT_SETTINGS)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                settings.update(saved)
            except Exception:
                pass
        return settings

    @staticmethod
    def save_settings(settings: dict):
        try:
            path = SettingsDialog._settings_path()
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
