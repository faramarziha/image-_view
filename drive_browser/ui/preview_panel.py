"""
Preview panel: High-performance preview for images, animated GIFs, and videos.
- Images & GIFs: Zoomable, pannable viewer with EXIF auto-transform and smooth scaling.
- Videos: Hardware-accelerated playback using QMediaPlayer, QAudioOutput, and QVideoWidget.
- Full controls: Play/pause, seek slider, duration/position timestamps, volume, and mute.
- Unicode path support: Uses QUrl.fromLocalFile to cleanly handle Persian and non-ASCII paths.
- Resilient fallback: Shows thumbnail and 'Open in default player' button if playback fails.
- Resource management: Stops and releases media when navigating, clearing, or closing.
- Slideshow: Waits for video playback to finish before advancing to the next file.
"""
from __future__ import annotations

import logging
import os
import subprocess
from typing import Optional

from PySide6.QtCore import (
    Qt, Signal, QTimer, QPoint, QRectF, QSize, QUrl,
)
from PySide6.QtGui import (
    QPixmap, QImageReader, QPainter, QWheelEvent, QMouseEvent,
    QKeyEvent, QMovie, QFont, QColor, QDesktopServices,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QSpinBox, QFrame, QScrollArea, QGraphicsView,
    QGraphicsScene, QGraphicsPixmapItem, QSizePolicy, QStackedWidget,
    QApplication
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

from core.models import FileEntry
from core.data_store import DataStore
from services.thumbnail_service import ThumbnailService, _extract_video_frame_ffmpeg

logger = logging.getLogger(__name__)


def _format_time_ms(ms: int) -> str:
    """Format milliseconds into MM:SS or HH:MM:SS string."""
    seconds = max(0, ms // 1000)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class ImageViewer(QGraphicsView):
    """
    Zoomable, pannable image viewer using QGraphicsView.
    Supports mouse wheel zoom, click-drag pan, and animated GIFs.
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

        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.gif':
            return self._show_gif(file_path)

        reader = QImageReader(file_path)
        reader.setAutoTransform(True)
        image = reader.read()

        if image.isNull():
            self._show_error(f"Cannot load: {reader.errorString()}")
            return False

        pixmap = QPixmap.fromImage(image)
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))

        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
        self._zoom_factor = 1.0
        return True

    def show_pixmap(self, pixmap: QPixmap):
        """Display an existing QPixmap."""
        self._stop_movie()
        self._scene.clear()
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
        self._zoom_factor = 1.0

    def _show_gif(self, file_path: str) -> bool:
        self._stop_movie()
        self._scene.clear()

        self._movie = QMovie(file_path)
        if not self._movie.isValid():
            self._show_error("Cannot load GIF")
            return False

        self._movie.jumpToFrame(0)
        pixmap = self._movie.currentPixmap()
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))

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
        self._scene.clear()
        text_item = self._scene.addText(message, QFont("Segoe UI", 14))
        text_item.setDefaultTextColor(QColor(200, 100, 100))

    def wheelEvent(self, event: QWheelEvent):
        factor = 1.15
        if event.angleDelta().y() > 0:
            self.scale(factor, factor)
            self._zoom_factor *= factor
        else:
            self.scale(1 / factor, 1 / factor)
            self._zoom_factor /= factor

    def fit_to_view(self):
        if self._scene.sceneRect().isValid():
            self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
            self._zoom_factor = 1.0

    def zoom_original(self):
        self.resetTransform()
        self._zoom_factor = 1.0

    def clear_view(self):
        self._stop_movie()
        self._scene.clear()
        self._pixmap_item = None


class VideoPlayerWidget(QWidget):
    """
    Video player widget embedding QVideoWidget with a sleek playback control bar.
    """
    playback_finished = Signal()
    playback_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._media_player: Optional[QMediaPlayer] = None
        self._audio_output: Optional[QAudioOutput] = None
        self._video_widget: Optional[QVideoWidget] = None
        self._is_user_seeking = False
        self._setup_ui()
        self._init_player()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Video output canvas
        self._video_widget = QVideoWidget(self)
        self._video_widget.setStyleSheet("background-color: #0d0d1a;")
        layout.addWidget(self._video_widget, 1)

        # ─── Control Bar ───
        controls_frame = QFrame(self)
        controls_frame.setStyleSheet("background-color: #16213e; border-radius: 6px; padding: 4px;")
        controls_layout = QHBoxLayout(controls_frame)
        controls_layout.setContentsMargins(8, 4, 8, 4)
        controls_layout.setSpacing(8)

        # Play / Pause
        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedWidth(36)
        self._play_btn.clicked.connect(self._toggle_play)
        controls_layout.addWidget(self._play_btn)

        # Seek slider
        self._seek_slider = QSlider(Qt.Horizontal)
        self._seek_slider.setRange(0, 0)
        self._seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self._seek_slider.sliderMoved.connect(self._on_seek_moved)
        self._seek_slider.sliderReleased.connect(self._on_seek_released)
        controls_layout.addWidget(self._seek_slider, 1)

        # Time label
        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setStyleSheet("font-size: 11px; font-family: monospace; color: #bbb;")
        controls_layout.addWidget(self._time_label)

        # Mute button
        self._mute_btn = QPushButton("🔊")
        self._mute_btn.setFixedWidth(36)
        self._mute_btn.clicked.connect(self._toggle_mute)
        controls_layout.addWidget(self._mute_btn)

        # Volume slider
        self._vol_slider = QSlider(Qt.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(80)
        self._vol_slider.setMaximumWidth(80)
        self._vol_slider.valueChanged.connect(self._on_volume_changed)
        controls_layout.addWidget(self._vol_slider)

        layout.addWidget(controls_frame)

    def _init_player(self):
        try:
            self._media_player = QMediaPlayer(self)
            self._audio_output = QAudioOutput(self)
            self._media_player.setAudioOutput(self._audio_output)
            self._media_player.setVideoOutput(self._video_widget)

            self._audio_output.setVolume(self._vol_slider.value() / 100.0)

            # Connect signals
            self._media_player.positionChanged.connect(self._on_position_changed)
            self._media_player.durationChanged.connect(self._on_duration_changed)
            self._media_player.playbackStateChanged.connect(self._on_playback_state_changed)
            self._media_player.mediaStatusChanged.connect(self._on_media_status_changed)
            self._media_player.errorOccurred.connect(self._on_error_occurred)

        except Exception as exc:
            logger.error("Failed to initialize QMediaPlayer: %s", exc)

    def load_video(self, file_path: str):
        if not self._media_player:
            self.playback_error.emit("Multimedia player not initialized")
            return

        self.stop()
        url = QUrl.fromLocalFile(file_path)
        self._media_player.setSource(url)
        self._media_player.play()

    def _toggle_play(self):
        if not self._media_player:
            return
        if self._media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._media_player.pause()
        else:
            self._media_player.play()

    def _toggle_mute(self):
        if not self._audio_output:
            return
        new_muted = not self._audio_output.isMuted()
        self._audio_output.setMuted(new_muted)
        self._mute_btn.setText("🔇" if new_muted else "🔊")

    def _on_volume_changed(self, value: int):
        if self._audio_output:
            self._audio_output.setVolume(value / 100.0)
            if self._audio_output.isMuted() and value > 0:
                self._audio_output.setMuted(False)
                self._mute_btn.setText("🔊")

    def _on_seek_pressed(self):
        self._is_user_seeking = True

    def _on_seek_moved(self, position: int):
        dur = self._seek_slider.maximum()
        self._time_label.setText(f"{_format_time_ms(position)} / {_format_time_ms(dur)}")

    def _on_seek_released(self):
        self._is_user_seeking = False
        if self._media_player:
            self._media_player.setPosition(self._seek_slider.value())

    def _on_position_changed(self, pos: int):
        if not self._is_user_seeking:
            self._seek_slider.setValue(pos)
            dur = self._seek_slider.maximum()
            self._time_label.setText(f"{_format_time_ms(pos)} / {_format_time_ms(dur)}")

    def _on_duration_changed(self, duration: int):
        self._seek_slider.setRange(0, duration)
        pos = self._seek_slider.value()
        self._time_label.setText(f"{_format_time_ms(pos)} / {_format_time_ms(duration)}")

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._play_btn.setText("⏸")
        else:
            self._play_btn.setText("▶")

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.playback_finished.emit()

    def _on_error_occurred(self, error: QMediaPlayer.Error, error_string: str):
        logger.warning("Video playback error (%s): %s", error, error_string)
        self.playback_error.emit(error_string)

    def stop(self):
        """Completely stop and release media source."""
        if self._media_player:
            self._media_player.stop()
            self._media_player.setSource(QUrl())
        self._seek_slider.setValue(0)
        self._seek_slider.setRange(0, 0)
        self._time_label.setText("00:00 / 00:00")
        self._play_btn.setText("▶")

    @property
    def is_playing(self) -> bool:
        return (
            self._media_player is not None
            and self._media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )


class VideoFallbackWidget(QWidget):
    """
    Fallback view displayed when video backend is unavailable or decoder errors occur.
    Shows the thumbnail frame, informative error banner, and a button to launch in default player.
    """
    open_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Image preview
        self._image_viewer = ImageViewer(self)
        layout.addWidget(self._image_viewer, 1)

        # Banner card
        banner_frame = QFrame(self)
        banner_frame.setStyleSheet("background-color: rgba(233, 69, 96, 0.15); border: 1px solid #e94560; border-radius: 8px; padding: 8px;")
        banner_layout = QHBoxLayout(banner_frame)

        self._msg_label = QLabel("⚠️ پخش ممکن نیست؛ Open in default player")
        self._msg_label.setStyleSheet("color: #ff6b81; font-weight: bold; font-size: 13px;")
        banner_layout.addWidget(self._msg_label, 1)

        self._open_btn = QPushButton("🎬 Open in default player")
        self._open_btn.setStyleSheet("background-color: #e94560; color: white; padding: 6px 12px; font-weight: bold;")
        self._open_btn.clicked.connect(self.open_requested.emit)
        banner_layout.addWidget(self._open_btn)

        layout.addWidget(banner_frame)

    def show_fallback(self, file_path: str, thumbnail_pixmap: Optional[QPixmap] = None):
        if thumbnail_pixmap and not thumbnail_pixmap.isNull():
            self._image_viewer.show_pixmap(thumbnail_pixmap)
        else:
            # Try to extract a video frame thumbnail with ffmpeg
            qimg = _extract_video_frame_ffmpeg(file_path, QSize(640, 480))
            if qimg is not None and not qimg.isNull():
                self._image_viewer.show_pixmap(QPixmap.fromImage(qimg))
            else:
                self._image_viewer.clear_view()
                self._image_viewer._show_error("🎬 Video Preview")


class PreviewPanel(QWidget):
    """
    Unified preview panel for images, animated GIFs, and videos.
    Integrates ImageViewer, VideoPlayerWidget, and VideoFallbackWidget with a QStackedWidget.
    """
    navigate_requested = Signal(int)  # -1 for prev, +1 for next
    close_requested = Signal()

    PAGE_IMAGE = 0
    PAGE_VIDEO = 1
    PAGE_FALLBACK = 2

    def __init__(
        self,
        data_store: DataStore,
        thumbnail_service: Optional[ThumbnailService] = None,
        parent=None
    ):
        super().__init__(parent)
        self._store = data_store
        self._thumb_service = thumbnail_service
        self._current_entry: Optional[FileEntry] = None
        self._current_file_path: str = ""

        # Slideshow timer
        self._slideshow_timer = QTimer(self)
        self._slideshow_timer.timeout.connect(self._advance_slideshow)
        self._is_slideshow_active = False

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ─── Top Toolbar ───
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self._close_btn = QPushButton("✕")
        self._close_btn.setMaximumWidth(32)
        self._close_btn.setToolTip("Close preview")
        self._close_btn.clicked.connect(self._on_close)
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

        # Image Zoom controls (only enabled for images)
        self._fit_btn = QPushButton("Fit")
        self._fit_btn.setMaximumWidth(50)
        self._fit_btn.clicked.connect(self._on_fit)
        toolbar.addWidget(self._fit_btn)

        self._orig_btn = QPushButton("100%")
        self._orig_btn.setMaximumWidth(50)
        self._orig_btn.clicked.connect(self._on_original)
        toolbar.addWidget(self._orig_btn)

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

        # ─── Stacked Viewers (Image | Video | Fallback) ───
        self._stack = QStackedWidget(self)

        # Page 0: ImageViewer
        self._image_viewer = ImageViewer(self)
        self._stack.addWidget(self._image_viewer)

        # Page 1: VideoPlayerWidget
        self._video_player = VideoPlayerWidget(self)
        self._video_player.playback_finished.connect(self._on_video_playback_finished)
        self._video_player.playback_error.connect(self._on_video_error)
        self._stack.addWidget(self._video_player)

        # Page 2: VideoFallbackWidget
        self._fallback_widget = VideoFallbackWidget(self)
        self._fallback_widget.open_requested.connect(self._open_in_default_player)
        self._stack.addWidget(self._fallback_widget)

        layout.addWidget(self._stack, 1)

    def show_entry(self, entry: FileEntry) -> None:
        """Display a file entry in the preview (image, GIF, or video)."""
        # Always cleanly stop any active video first
        self._video_player.stop()

        self._current_entry = entry
        file_path = self._store.get_actual_path(entry)
        self._current_file_path = file_path

        # Update info label
        icon = "🎬" if entry.is_video() else ("🖼️" if entry.is_image() else "📄")
        self._info_label.setText(
            f"{icon} {entry.name}  |  {entry.size_display}  |  "
            f"{entry.date_display}  |  {entry.folder}"
        )

        if entry.is_video():
            # Video display
            self._fit_btn.setEnabled(False)
            self._orig_btn.setEnabled(False)

            if not os.path.isfile(file_path):
                self._show_video_fallback(file_path)
                return

            self._stack.setCurrentIndex(self.PAGE_VIDEO)
            self._video_player.load_video(file_path)

            # In slideshow mode: pause slideshow timer so video plays through
            if self._is_slideshow_active:
                self._slideshow_timer.stop()
        else:
            # Image / GIF display
            self._fit_btn.setEnabled(True)
            self._orig_btn.setEnabled(True)
            self._stack.setCurrentIndex(self.PAGE_IMAGE)
            self._image_viewer.show_image(file_path)

            if self._is_slideshow_active:
                interval_ms = self._slide_interval.value() * 1000
                self._slideshow_timer.start(interval_ms)

    def _show_video_fallback(self, file_path: str):
        """Show fallback preview when video cannot be played."""
        self._video_player.stop()
        self._stack.setCurrentIndex(self.PAGE_FALLBACK)

        thumb_pixmap = None
        if self._thumb_service is not None:
            thumb_pixmap = self._thumb_service.request_thumbnail(file_path)

        self._fallback_widget.show_fallback(file_path, thumb_pixmap)

        # If slideshow is active, restart slideshow timer so it doesn't get stuck on missing/unplayable videos
        if self._is_slideshow_active:
            interval_ms = self._slide_interval.value() * 1000
            self._slideshow_timer.start(interval_ms)

    def _on_video_error(self, error_msg: str):
        """Handle video playback error gracefully with fallback."""
        if self._current_file_path:
            self._show_video_fallback(self._current_file_path)
        elif self._is_slideshow_active:
            interval_ms = self._slide_interval.value() * 1000
            self._slideshow_timer.start(interval_ms)

    def _on_video_playback_finished(self):
        """Handle video reaching EndOfMedia."""
        if self._is_slideshow_active:
            # Advance to next slide once video completes
            self.navigate_requested.emit(1)

    def clear(self):
        """Clear viewer and cleanly stop and release video resources."""
        self._video_player.stop()
        self._image_viewer.clear_view()
        self._info_label.setText("")
        self._current_entry = None
        self._current_file_path = ""
        self._stack.setCurrentIndex(self.PAGE_IMAGE)

    def _on_close(self):
        self.clear()
        self.close_requested.emit()

    def closeEvent(self, event):
        self.clear()
        event.accept()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Left:
            self.navigate_requested.emit(-1)
        elif event.key() == Qt.Key_Right:
            self.navigate_requested.emit(1)
        elif event.key() == Qt.Key_Escape:
            self._on_close()
        elif event.key() == Qt.Key_Space:
            if self._stack.currentIndex() == self.PAGE_VIDEO:
                self._video_player._toggle_play()
            else:
                self._toggle_slideshow(not self._is_slideshow_active)
        elif event.key() == Qt.Key_F:
            if self._stack.currentIndex() == self.PAGE_IMAGE:
                self._on_fit()
        elif event.key() == Qt.Key_1:
            if self._stack.currentIndex() == self.PAGE_IMAGE:
                self._on_original()
        elif event.key() == Qt.Key_M:
            if self._stack.currentIndex() == self.PAGE_VIDEO:
                self._video_player._toggle_mute()
        else:
            super().keyPressEvent(event)

    def _on_fit(self):
        self._image_viewer.fit_to_view()

    def _on_original(self):
        self._image_viewer.zoom_original()

    def _toggle_slideshow(self, active: bool):
        self._is_slideshow_active = active
        self._slide_btn.setChecked(active)

        if active:
            self._slide_btn.setText("⏸ Pause")
            if self._current_entry and self._current_entry.is_video():
                if self._stack.currentIndex() == self.PAGE_FALLBACK or not os.path.isfile(self._current_file_path):
                    interval_ms = self._slide_interval.value() * 1000
                    self._slideshow_timer.start(interval_ms)
                else:
                    # Let video play to end; don't start timer
                    self._slideshow_timer.stop()
            else:
                interval_ms = self._slide_interval.value() * 1000
                self._slideshow_timer.start(interval_ms)
        else:
            self._slideshow_timer.stop()
            self._slide_btn.setText("▶ Play")

    def _advance_slideshow(self):
        if self._is_slideshow_active:
            self.navigate_requested.emit(1)

    def _open_in_explorer(self):
        if self._current_file_path:
            if os.path.isfile(self._current_file_path):
                subprocess.run(['explorer', f'/select,{self._current_file_path}'], check=False)
            else:
                folder = os.path.dirname(self._current_file_path)
                if os.path.isdir(folder):
                    os.startfile(folder)

    def _open_in_default_player(self):
        if self._current_file_path and os.path.isfile(self._current_file_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._current_file_path))
