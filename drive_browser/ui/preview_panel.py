"""
Preview panel: large image preview with zoom, pan, and slideshow.
Handles images (jpg, png, bmp, tif), animated GIFs, and video thumbnails.
"""
from __future__ import annotations

import os

from PySide6.QtCore import (
    Qt, Signal, QTimer, QPoint, QRectF, QSize,
)
from PySide6.QtGui import (
    QPixmap, QImageReader, QPainter, QWheelEvent, QMouseEvent,
    QKeyEvent, QMovie, QFont, QColor,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QSpinBox, QFrame, QScrollArea, QGraphicsView,
    QGraphicsScene, QGraphicsPixmapItem, QSizePolicy,
)

from core.models import FileEntry
from core.data_store import DataStore


class ImageViewer(QGraphicsView):
    """
    Zoomable, pannable image viewer using QGraphicsView.
    Supports mouse wheel zoom and click-drag pan.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._movie: QMovie | None = None
        self._zoom_factor = 1.0

        # Setup
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setBackgroundBrush(QColor(20, 20, 35))
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setRenderHint(QPainter.Antialiasing)

    def show_image(self, file_path: str) -> bool:
        """Load and display an image file. Returns True if successful."""
        self._stop_movie()
        self._scene.clear()
        self._pixmap_item = None

        if not os.path.isfile(file_path):
            self._show_error("File not found")
            return False

        # Check if it's a GIF for animation
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.gif':
            return self._show_gif(file_path)

        # Load image with EXIF auto-transform
        reader = QImageReader(file_path)
        reader.setAutoTransform(True)
        image = reader.read()

        if image.isNull():
            self._show_error(f"Cannot load: {reader.errorString()}")
            return False

        pixmap = QPixmap.fromImage(image)
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))

        # Fit in view
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
        self._zoom_factor = 1.0
        return True

    def _show_gif(self, file_path: str) -> bool:
        """Display animated GIF."""
        self._stop_movie()
        self._scene.clear()

        self._movie = QMovie(file_path)
        if not self._movie.isValid():
            self._show_error("Cannot load GIF")
            return False

        # Create a pixmap item that we'll update on each frame
        self._movie.jumpToFrame(0)
        pixmap = self._movie.currentPixmap()
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))

        # Connect frame updates
        self._movie.frameChanged.connect(self._on_gif_frame)
        self._movie.start()

        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
        self._zoom_factor = 1.0
        return True

    def _on_gif_frame(self):
        if self._pixmap_item and self._movie:
            self._pixmap_item.setPixmap(self._movie.currentPixmap())

    def _stop_movie(self):
        if self._movie:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None

    def _show_error(self, message: str):
        """Show error text in the view."""
        self._scene.clear()
        text_item = self._scene.addText(message, QFont("Segoe UI", 14))
        text_item.setDefaultTextColor(QColor(200, 100, 100))

    def wheelEvent(self, event: QWheelEvent):
        """Zoom in/out with mouse wheel."""
        factor = 1.15
        if event.angleDelta().y() > 0:
            self.scale(factor, factor)
            self._zoom_factor *= factor
        else:
            self.scale(1 / factor, 1 / factor)
            self._zoom_factor /= factor

    def fit_to_view(self):
        """Reset zoom to fit image in view."""
        if self._scene.sceneRect().isValid():
            self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
            self._zoom_factor = 1.0

    def zoom_original(self):
        """Show at 100% zoom."""
        self.resetTransform()
        self._zoom_factor = 1.0

    def clear_view(self):
        """Clear the current display."""
        self._stop_movie()
        self._scene.clear()
        self._pixmap_item = None


class PreviewPanel(QWidget):
    """
    Preview panel with large image viewer, navigation buttons, and slideshow.
    """
    navigate_requested = Signal(int)  # -1 for prev, +1 for next
    close_requested = Signal()

    def __init__(self, data_store: DataStore, parent=None):
        super().__init__(parent)
        self._store = data_store
        self._current_entry: FileEntry | None = None
        self._slideshow_timer = QTimer(self)
        self._slideshow_timer.timeout.connect(lambda: self.navigate_requested.emit(1))
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ─── Toolbar ───
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self._close_btn = QPushButton("✕")
        self._close_btn.setMaximumWidth(32)
        self._close_btn.setToolTip("Close preview")
        self._close_btn.clicked.connect(self.close_requested.emit)
        toolbar.addWidget(self._close_btn)

        self._info_label = QLabel("")
        self._info_label.setStyleSheet("font-size: 12px; padding: 0 8px;")
        toolbar.addWidget(self._info_label, 1)

        # Navigation
        self._prev_btn = QPushButton("◀ Prev")
        self._prev_btn.clicked.connect(lambda: self.navigate_requested.emit(-1))
        toolbar.addWidget(self._prev_btn)

        self._next_btn = QPushButton("Next ▶")
        self._next_btn.clicked.connect(lambda: self.navigate_requested.emit(1))
        toolbar.addWidget(self._next_btn)

        # Zoom controls
        fit_btn = QPushButton("Fit")
        fit_btn.setMaximumWidth(50)
        fit_btn.clicked.connect(self._on_fit)
        toolbar.addWidget(fit_btn)

        orig_btn = QPushButton("100%")
        orig_btn.setMaximumWidth(50)
        orig_btn.clicked.connect(self._on_original)
        toolbar.addWidget(orig_btn)

        # Slideshow
        toolbar.addWidget(QLabel("Slide:"))
        self._slide_interval = QSpinBox()
        self._slide_interval.setRange(1, 60)
        self._slide_interval.setValue(3)
        self._slide_interval.setSuffix("s")
        self._slide_interval.setMaximumWidth(70)
        toolbar.addWidget(self._slide_interval)

        self._slide_btn = QPushButton("▶ Play")
        self._slide_btn.setCheckable(True)
        self._slide_btn.toggled.connect(self._toggle_slideshow)
        toolbar.addWidget(self._slide_btn)

        # Open in Explorer
        self._open_btn = QPushButton("📂 Show in folder")
        self._open_btn.clicked.connect(self._open_in_explorer)
        toolbar.addWidget(self._open_btn)

        layout.addLayout(toolbar)

        # ─── Image viewer ───
        self._viewer = ImageViewer()
        layout.addWidget(self._viewer, 1)

    def show_entry(self, entry: FileEntry) -> None:
        """Display a file entry in the preview."""
        self._current_entry = entry
        file_path = self._store.get_file_full_path(entry)

        # Update info label
        self._info_label.setText(
            f"📄 {entry.name}  |  {entry.size_display}  |  "
            f"{entry.date_display}  |  {entry.folder}"
        )

        # Show image
        self._viewer.show_image(file_path)

    def clear(self):
        self._viewer.clear_view()
        self._info_label.setText("")
        self._current_entry = None

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Left:
            self.navigate_requested.emit(-1)
        elif event.key() == Qt.Key_Right:
            self.navigate_requested.emit(1)
        elif event.key() == Qt.Key_Escape:
            self.close_requested.emit()
        elif event.key() == Qt.Key_F:
            self._on_fit()
        elif event.key() == Qt.Key_1:
            self._on_original()
        else:
            super().keyPressEvent(event)

    def _on_fit(self):
        self._viewer.fit_to_view()

    def _on_original(self):
        self._viewer.zoom_original()

    def _toggle_slideshow(self, active: bool):
        if active:
            interval_ms = self._slide_interval.value() * 1000
            self._slideshow_timer.start(interval_ms)
            self._slide_btn.setText("⏸ Pause")
        else:
            self._slideshow_timer.stop()
            self._slide_btn.setText("▶ Play")

    def _open_in_explorer(self):
        """Open the file's folder in Windows Explorer."""
        if self._current_entry:
            path = self._store.get_file_full_path(self._current_entry)
            if os.path.isfile(path):
                os.system(f'explorer /select,"{path}"')
            else:
                folder = os.path.dirname(path)
                if os.path.isdir(folder):
                    os.startfile(folder)
