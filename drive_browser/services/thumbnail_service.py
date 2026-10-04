"""
Thumbnail service: generates thumbnails asynchronously using a thread pool.
- Creates QImage in worker threads; converts to QPixmap exclusively on main thread.
- Uses Qt.AspectRatioMode.KeepAspectRatio and logs actual exception messages.
- Caches failed paths (file not found, corrupt) so they are not re-requested.
- Prioritizes newer items (LIFO) and supports cancelling out-of-view requests.
- Supports Unicode paths with OpenCV (np.fromfile + cv2.imdecode).
- Supports video thumbnail generation via ffmpeg subprocess (fallback to OpenCV/placeholder).
- Supports Windows long paths with \\?\\ prefix.
- Configurable LRU cache with default limit of 256 MB.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from collections import OrderedDict
from typing import Optional, Set, Dict, List

from PySide6.QtCore import (
    QObject, QRunnable, QThreadPool, Signal, Slot, QSize, QMutex, QMutexLocker, Qt,
)
from PySide6.QtGui import QImage, QImageReader, QPixmap

logger = logging.getLogger(__name__)

# Common video extensions
VIDEO_EXTENSIONS = {
    '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv',
    '.webm', '.3gp', '.m4v', '.ts', '.mpg', '.mpeg', '.vob'
}


def normalize_long_path(file_path: str) -> str:
    """
    Ensure long paths (>260 chars) on Windows have the \\?\\ prefix.
    """
    if not file_path:
        return file_path
    if os.name == 'nt':
        abs_path = os.path.abspath(file_path)
        if not abs_path.startswith('\\\\?\\') and not abs_path.startswith('\\\\.\\'):
            if abs_path.startswith('\\\\'):
                # UNC path: \\server\share -> \\?\UNC\server\share
                return '\\\\?\\UNC\\' + abs_path[2:]
            return '\\\\?\\' + abs_path
        return abs_path
    return os.path.abspath(file_path)


def _extract_video_frame_ffmpeg(video_path: str, target_size: QSize) -> Optional[QImage]:
    """
    Extract a thumbnail frame from video using ffmpeg subprocess.
    Falls back to OpenCV VideoCapture if ffmpeg is unavailable.
    """
    # 1. Try ffmpeg subprocess
    w = max(32, target_size.width())
    h = max(32, target_size.height())
    cmd = [
        "ffmpeg",
        "-ss", "00:00:01",
        "-i", video_path,
        "-vframes", "1",
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease",
        "-f", "image2pipe",
        "-vcodec", "png",
        "-"
    ]
    creationflags = 0x08000000 if sys.platform == 'win32' else 0
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            timeout=4
        )
        if proc.returncode == 0 and proc.stdout:
            img = QImage()
            if img.loadFromData(proc.stdout, "PNG"):
                return img
    except FileNotFoundError:
        logger.debug("ffmpeg executable not found in PATH for video thumbnail")
    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg timed out extracting frame from: %s", video_path)
    except Exception as exc:
        logger.warning("ffmpeg error extracting frame from %s: %s", video_path, exc)

    # 2. Fallback to OpenCV cv2.VideoCapture
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_POS_MSEC, 1000)
            ret, frame = cap.read()
            if not ret or frame is None:
                cap.set(cv2.CAP_PROP_POS_MSEC, 0)
                ret, frame = cap.read()
            cap.release()
            if ret and frame is not None:
                fh, fw = frame.shape[:2]
                scale = min(w / max(fw, 1), h / max(fh, 1))
                nw, nh = max(1, int(fw * scale)), max(1, int(fh * scale))
                resized = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)
                rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                rh, rw, ch = rgb.shape
                return QImage(rgb.data, rw, rh, ch * rw, QImage.Format_RGB888).copy()
    except Exception as cv_vid_err:
        logger.warning("OpenCV video capture failed for %s: %s", video_path, cv_vid_err)

    return None


def _read_image_opencv(file_path: str, target_size: QSize) -> Optional[QImage]:
    """
    Read image using OpenCV with np.fromfile and cv2.imdecode to robustly handle Unicode paths.
    """
    try:
        import cv2
        import numpy as np

        # np.fromfile handles Unicode paths cleanly on Windows
        raw_bytes = None
        for p in (normalize_long_path(file_path), file_path):
            try:
                raw_bytes = np.fromfile(p, dtype=np.uint8)
                if raw_bytes is not None and len(raw_bytes) > 0:
                    break
            except Exception:
                continue

        if raw_bytes is None or len(raw_bytes) == 0:
            return None

        mat = cv2.imdecode(raw_bytes, cv2.IMREAD_COLOR)
        if mat is None:
            return None

        mh, mw = mat.shape[:2]
        tw = max(16, target_size.width())
        th = max(16, target_size.height())
        scale = min(tw / max(mw, 1), th / max(mh, 1))
        nw = max(1, int(mw * scale))
        nh = max(1, int(mh * scale))

        mat_resized = cv2.resize(mat, (nw, nh), interpolation=cv2.INTER_AREA)
        mat_rgb = cv2.cvtColor(mat_resized, cv2.COLOR_BGR2RGB)
        rh, rw, ch = mat_rgb.shape
        return QImage(mat_rgb.data, rw, rh, ch * rw, QImage.Format_RGB888).copy()

    except Exception as exc:
        logger.warning("OpenCV image decode failed for %s: %s", file_path, exc)
        return None


class ThumbnailResult:
    """Result of a thumbnail generation task containing only QImage."""
    __slots__ = ('file_path', 'image', 'error')

    def __init__(self, file_path: str, image: Optional[QImage] = None, error: str = ''):
        self.file_path = file_path
        self.image = image
        self.error = error


class ThumbnailSignals(QObject):
    """Signals for thumbnail worker communication."""
    finished = Signal(object)  # ThumbnailResult


class ThumbnailWorker(QRunnable):
    """
    Worker that generates a single thumbnail as QImage in a background thread.
    Conversion to QPixmap is strictly left to the main GUI thread.
    """

    def __init__(self, file_path: str, target_size: QSize):
        super().__init__()
        self.file_path = file_path
        self.target_size = target_size
        self.signals = ThumbnailSignals()
        self._cancelled = False
        self.setAutoDelete(True)

    def cancel(self):
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    @Slot()
    def run(self):
        if self._cancelled:
            return

        norm_path = normalize_long_path(self.file_path)

        try:
            # Check existence with both paths
            if not os.path.isfile(norm_path) and not os.path.isfile(self.file_path):
                err = f"File not found: {self.file_path}"
                logger.warning(err)
                if not self._cancelled:
                    self.signals.finished.emit(ThumbnailResult(self.file_path, error=err))
                return

            ext = os.path.splitext(self.file_path)[1].lower()

            # Video thumbnail handling
            if ext in VIDEO_EXTENSIONS:
                img = _extract_video_frame_ffmpeg(self.file_path, self.target_size)
                if self._cancelled:
                    return
                if img is not None and not img.isNull():
                    self.signals.finished.emit(ThumbnailResult(self.file_path, image=img))
                else:
                    err = f"Video thumbnail generation failed for {self.file_path}"
                    logger.warning(err)
                    self.signals.finished.emit(ThumbnailResult(self.file_path, error=err))
                return

            # Image thumbnail handling: Try QImageReader first
            image: Optional[QImage] = None
            reader = QImageReader(norm_path)
            reader.setAutoTransform(True)

            original_size = reader.size()
            if original_size.isValid():
                scaled_size = original_size.scaled(self.target_size, Qt.AspectRatioMode.KeepAspectRatio)
                reader.setScaledSize(scaled_size)
                qimg = reader.read()
                if not qimg.isNull():
                    image = qimg
                else:
                    logger.debug("QImageReader null image for %s: %s", self.file_path, reader.errorString())

            # Fallback to OpenCV with np.fromfile (handles Unicode & special image files)
            if (image is None or image.isNull()) and not self._cancelled:
                image = _read_image_opencv(self.file_path, self.target_size)

            if self._cancelled:
                return

            if image is not None and not image.isNull():
                self.signals.finished.emit(ThumbnailResult(self.file_path, image=image))
            else:
                err = f"Failed to decode image: {self.file_path}"
                logger.warning(err)
                self.signals.finished.emit(ThumbnailResult(self.file_path, error=err))

        except Exception as exc:
            logger.warning("Exception generating thumbnail for %s: %s", self.file_path, exc, exc_info=True)
            if not self._cancelled:
                self.signals.finished.emit(ThumbnailResult(self.file_path, error=str(exc)))


class ThumbnailCache:
    """
    Thread-safe LRU cache for QPixmaps in RAM.
    Evicts oldest entries when memory limit is exceeded.
    Default max memory: 256 MB.
    """

    def __init__(self, max_memory_mb: int = 256):
        self._cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._mutex = QMutex()
        self._current_memory = 0  # Approximate bytes
        self._max_memory = max_memory_mb * 1024 * 1024

    def get(self, key: str) -> Optional[QPixmap]:
        locker = QMutexLocker(self._mutex)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: str, pixmap: QPixmap) -> None:
        locker = QMutexLocker(self._mutex)
        if key in self._cache:
            self._current_memory -= self._estimate_pixmap_size(self._cache[key])
            del self._cache[key]

        size = self._estimate_pixmap_size(pixmap)
        self._cache[key] = pixmap
        self._current_memory += size

        while self._current_memory > self._max_memory and self._cache:
            oldest_key, oldest_pixmap = self._cache.popitem(last=False)
            self._current_memory -= self._estimate_pixmap_size(oldest_pixmap)

    def contains(self, key: str) -> bool:
        locker = QMutexLocker(self._mutex)
        return key in self._cache

    def clear(self):
        locker = QMutexLocker(self._mutex)
        self._cache.clear()
        self._current_memory = 0

    @staticmethod
    def _estimate_pixmap_size(pixmap: QPixmap) -> int:
        if pixmap.isNull():
            return 0
        depth = pixmap.depth() if pixmap.depth() > 0 else 32
        return pixmap.width() * pixmap.height() * (depth // 8)

    @property
    def usage_info(self) -> str:
        locker = QMutexLocker(self._mutex)
        used_mb = self._current_memory / (1024 * 1024)
        max_mb = self._max_memory / (1024 * 1024)
        return f"{len(self._cache)} items, {used_mb:.1f}/{max_mb:.0f} MB"


class ThumbnailService(QObject):
    """
    High-level service for requesting thumbnails:
    - Default cache limit: 256 MB.
    - Caches failures so unreadable/missing files are never re-requested.
    - Priority queue: newest items dispatched first (LIFO).
    - Can cancel pending or active requests for out-of-view items.
    - Converts QImage to QPixmap safely on the main Qt GUI thread.
    """
    thumbnail_ready = Signal(str, object)  # (file_path, QPixmap or None)

    def __init__(self, thumbnail_size: int = 200, max_cache_mb: int = 256, parent=None):
        super().__init__(parent)
        self._thumbnail_size = QSize(thumbnail_size, thumbnail_size)
        self._cache = ThumbnailCache(max_cache_mb)
        self._failed_paths: Set[str] = set()

        # Task scheduling: LIFO pending queue
        self._pending_queue: List[str] = []
        self._pending_set: Set[str] = set()
        self._active_workers: Dict[str, ThumbnailWorker] = {}

        self._pool = QThreadPool.globalInstance()
        self._max_workers = min(4, max(2, (os.cpu_count() or 4) - 1))
        self._pool.setMaxThreadCount(self._max_workers)
        self._mutex = QMutex()

    @property
    def thumbnail_size(self) -> QSize:
        return self._thumbnail_size

    @thumbnail_size.setter
    def thumbnail_size(self, size: int):
        self._thumbnail_size = QSize(size, size)

    def request_thumbnail(self, file_path: str) -> Optional[QPixmap]:
        """
        Request a thumbnail for the given file path.
        Returns cached QPixmap immediately if present.
        Returns None and initiates async generation if not cached.
        Ignores previously failed paths to prevent repeated work.
        """
        if not file_path:
            return None

        # 1. Fast check for known failures
        locker = QMutexLocker(self._mutex)
        if file_path in self._failed_paths:
            return None

        # 2. Check LRU Cache
        cached = self._cache.get(file_path)
        if cached is not None:
            return cached

        # 3. Already actively running in worker
        if file_path in self._active_workers:
            return None

        # 4. If already queued, move to the top (LIFO: newest request first)
        if file_path in self._pending_set:
            try:
                self._pending_queue.remove(file_path)
            except ValueError:
                pass
            self._pending_queue.append(file_path)
            locker.unlock()
            self._dispatch_next()
            return None

        # 5. Add to pending queue (pushed to end for LIFO pop)
        self._pending_set.add(file_path)
        self._pending_queue.append(file_path)
        locker.unlock()

        self._dispatch_next()
        return None

    def cancel_request(self, file_path: str) -> None:
        """Cancel a pending or running thumbnail request."""
        locker = QMutexLocker(self._mutex)
        if file_path in self._pending_set:
            try:
                self._pending_queue.remove(file_path)
            except ValueError:
                pass
            self._pending_set.discard(file_path)

        worker = self._active_workers.pop(file_path, None)
        if worker is not None:
            worker.cancel()
            self._pending_set.discard(file_path)

    def cancel_out_of_view(self, visible_paths: Set[str]) -> None:
        """
        Cancel pending requests that are no longer in the visible set.
        """
        locker = QMutexLocker(self._mutex)
        # Prune pending queue
        new_queue = [p for p in self._pending_queue if p in visible_paths]
        removed = set(self._pending_queue) - set(new_queue)
        self._pending_queue = new_queue
        for p in removed:
            self._pending_set.discard(p)

        # Cancel active workers that are out of view
        for p in list(self._active_workers.keys()):
            if p not in visible_paths:
                w = self._active_workers.pop(p, None)
                if w:
                    w.cancel()
                self._pending_set.discard(p)

    def _dispatch_next(self) -> None:
        """Dispatch pending requests up to max concurrency using LIFO order."""
        locker = QMutexLocker(self._mutex)
        while len(self._active_workers) < self._max_workers and self._pending_queue:
            # LIFO: pop from end (newest item)
            file_path = self._pending_queue.pop()

            worker = ThumbnailWorker(file_path, self._thumbnail_size)
            worker.signals.finished.connect(self._on_thumbnail_done)
            self._active_workers[file_path] = worker
            self._pool.start(worker)

    @Slot(object)
    def _on_thumbnail_done(self, result: ThumbnailResult):
        """
        Handle completed thumbnail generation.
        Strictly executed on the main GUI thread via Qt Signal/Slot.
        """
        locker = QMutexLocker(self._mutex)
        self._active_workers.pop(result.file_path, None)
        self._pending_set.discard(result.file_path)
        locker.unlock()

        if result.image and not result.image.isNull():
            # Convert QImage to QPixmap strictly on the main thread
            pixmap = QPixmap.fromImage(result.image)
            self._cache.put(result.file_path, pixmap)
            self.thumbnail_ready.emit(result.file_path, pixmap)
        else:
            # Cache failure so we don't attempt to re-read corrupted/missing files
            locker = QMutexLocker(self._mutex)
            self._failed_paths.add(result.file_path)
            locker.unlock()
            self.thumbnail_ready.emit(result.file_path, None)

        self._dispatch_next()

    def clear_cache(self):
        """Clear memory cache, failures, and cancel all queued requests."""
        locker = QMutexLocker(self._mutex)
        self._cache.clear()
        self._failed_paths.clear()
        self._pending_queue.clear()
        self._pending_set.clear()
        for worker in self._active_workers.values():
            worker.cancel()
        self._active_workers.clear()

    @property
    def cache_info(self) -> str:
        return self._cache.usage_info
