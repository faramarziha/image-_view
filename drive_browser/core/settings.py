"""
Settings management using QSettings for persistent application state:
- Recent files list
- Root path remapping (e.g. E:\\ -> F:\\)
- Theme preference (Dark / Light)
- Thumbnail cache size limit (default 256 MB)
- Thumbnail grid item size
- Window geometry / state
"""
from __future__ import annotations

import os
from typing import List, Optional
from PySide6.QtCore import QSettings


class AppSettings:
    """Wrapper around QSettings for typed configuration access."""

    ORGANIZATION = "DriveAnalyzer"
    APPLICATION = "DriveContentBrowser"

    # Default values
    DEFAULT_CACHE_SIZE_MB = 256
    DEFAULT_THUMBNAIL_SIZE = 160
    DEFAULT_THEME = "dark"
    DEFAULT_SLIDESHOW_INTERVAL = 3
    MAX_RECENT_FILES = 10

    def __init__(self):
        self._settings = QSettings(self.ORGANIZATION, self.APPLICATION)

    # ── Root Remap ──
    @property
    def root_remap(self) -> str:
        return self._settings.value("storage/root_remap", "", type=str)

    @root_remap.setter
    def root_remap(self, value: str):
        val = value.strip().replace("/", "\\")
        if val and not val.endswith("\\"):
            val += "\\"
        self._settings.setValue("storage/root_remap", val)

    # ── Cache Size ──
    @property
    def cache_size_mb(self) -> int:
        return self._settings.value("performance/cache_size_mb", self.DEFAULT_CACHE_SIZE_MB, type=int)

    @cache_size_mb.setter
    def cache_size_mb(self, value: int):
        self._settings.setValue("performance/cache_size_mb", max(64, min(4096, int(value))))

    # ── Thumbnail Size ──
    @property
    def thumbnail_size(self) -> int:
        return self._settings.value("ui/thumbnail_size", self.DEFAULT_THUMBNAIL_SIZE, type=int)

    @thumbnail_size.setter
    def thumbnail_size(self, value: int):
        self._settings.setValue("ui/thumbnail_size", max(80, min(400, int(value))))

    # ── Theme ──
    @property
    def theme(self) -> str:
        return self._settings.value("ui/theme", self.DEFAULT_THEME, type=str)

    @theme.setter
    def theme(self, value: str):
        self._settings.setValue("ui/theme", "light" if value.lower() == "light" else "dark")

    # ── Slideshow Interval ──
    @property
    def slideshow_interval(self) -> int:
        return self._settings.value("slideshow/interval_sec", self.DEFAULT_SLIDESHOW_INTERVAL, type=int)

    @slideshow_interval.setter
    def slideshow_interval(self, value: int):
        self._settings.setValue("slideshow/interval_sec", max(1, min(60, int(value))))

    # ── Recent Files ──
    @property
    def recent_files(self) -> List[str]:
        raw = self._settings.value("recent/files", [])
        if isinstance(raw, list):
            return [str(p) for p in raw if os.path.isfile(str(p))]
        return []

    def add_recent_file(self, file_path: str):
        normalized = os.path.abspath(file_path)
        current = self.recent_files
        if normalized in current:
            current.remove(normalized)
        current.insert(0, normalized)
        current = current[:self.MAX_RECENT_FILES]
        self._settings.setValue("recent/files", current)

    def clear_recent_files(self):
        self._settings.setValue("recent/files", [])

    # ── Window Geometry ──
    def save_window_state(self, geometry: bytes, state: bytes):
        self._settings.setValue("window/geometry", geometry)
        self._settings.setValue("window/state", state)

    def load_window_geometry(self) -> Optional[bytes]:
        val = self._settings.value("window/geometry")
        return bytes(val) if val else None

    def load_window_state(self) -> Optional[bytes]:
        val = self._settings.value("window/state")
        return bytes(val) if val else None
