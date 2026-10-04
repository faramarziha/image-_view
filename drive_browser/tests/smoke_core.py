"""
Comprehensive smoke test suite for core and service modules.
Run via: python tests/smoke_core.py or pytest tests/smoke_core.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.models import FileEntry, FolderNode, intern_folder, clear_folder_pool
from core.parser import (
    detect_file_encoding, parse_size_to_kb, parse_datetime,
    parse_single_line, parse_analyzer_file, ParseResult
)
from core.data_store import DataStore
from core.indexer import (
    build_folder_tree, build_duplicate_index,
    extract_unique_extensions, extract_unique_categories
)
from services.copy_service import (
    sanitize_windows_filename, is_subpath, CopyThread, ConflictAction, CopyResult
)
from services.thumbnail_service import normalize_long_path, ThumbnailCache
from services.availability_service import check_availability_sync


class TestParser(unittest.TestCase):
    """Test parser functions, encoding detection, and BOM stripping."""

    def test_utf16_bom_detection_and_stripping(self):
        """Verify that UTF-16 BOM returns 'utf-16' and \ufeff is completely stripped."""
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            # UTF-16 LE with BOM: \ufeffIMG_001.jpg \t E:\photo\ \t jpg \t 100 KB \t Pictures \t 8/22/2019 9:18:40 AM \t
            content = "IMG_001.jpg\tE:\\photo\\\tjpg\t100 KB\tPictures\t8/22/2019 9:18:40 AM\t\n"
            f.write(content.encode('utf-16'))
            tmp_path = f.name

        try:
            enc = detect_file_encoding(tmp_path)
            self.assertEqual(enc, 'utf-16', "Encoding must be 'utf-16' so Python strips BOM automatically")

            result = parse_analyzer_file(tmp_path)
            self.assertEqual(len(result.entries), 1)
            first_entry = result.entries[0]
            self.assertEqual(first_entry.name, "IMG_001.jpg")
            self.assertFalse(first_entry.name.startswith('\ufeff'), "Entry name must not start with BOM character \ufeff")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_leading_bom_explicit_stripping(self):
        """Test parse_single_line directly with an explicit \ufeff at start of string."""
        raw_line = "\ufefftest_file.png\tC:\\images\\\tpng\t50 KB\tPictures\t2020-01-01 12:00:00\t"
        entry = parse_single_line(raw_line, line_number=1, entry_index=0)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.name, "test_file.png")
        self.assertFalse(entry.name.startswith('\ufeff'))

    def test_utf8_split_character_detection(self):
        """Test that a UTF-8 character split right at the 64KB boundary doesn't error."""
        # Create a payload of ~65535 bytes of ASCII, followed by a 2-byte Persian character 'س' (\xd8\xb3)
        # whose first byte lands at byte 65535 and second byte at byte 65536
        padding = b'a' * 65535
        split_char = 'س'.encode('utf-8')  # 2 bytes: b'\xd8\xb3'
        payload = padding + split_char

        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            f.write(payload)
            tmp_path = f.name

        try:
            enc = detect_file_encoding(tmp_path)
            self.assertEqual(enc, 'utf-8', "Must detect utf-8 without throwing UnicodeDecodeError on split boundary")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_size_parsing(self):
        self.assertEqual(parse_size_to_kb("14,897 KB"), 14897.0)
        self.assertEqual(parse_size_to_kb("0.5 KB"), 0.5)
        self.assertIsNone(parse_size_to_kb("invalid"))

    def test_date_parsing(self):
        dt = parse_datetime("8/22/2019 9:18:40 AM")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2019)
        self.assertEqual(dt.month, 8)
        self.assertEqual(dt.day, 22)


class TestModelsAndDataStore(unittest.TestCase):
    """Test FileEntry, FolderNode, DataStore indexes, search and sorting."""

    def setUp(self):
        clear_folder_pool()

    def test_file_entry_properties(self):
        folder = intern_folder("E:\\photos\\2020\\")
        entry = FileEntry(
            index=0,
            name="IMG_100.jpg",
            folder=folder,
            extension="jpg",
            size_kb=1024.0,
            category="Pictures",
            date=datetime(2020, 5, 1, 10, 0, 0),
            line_number=1,
            is_available=True
        )
        self.assertEqual(entry.full_path, "E:\\photos\\2020\\IMG_100.jpg")
        self.assertEqual(entry.size_bytes, 1024 * 1024)
        self.assertEqual(entry.size_display, "1.0 MB")
        self.assertTrue(entry.is_image())
        self.assertFalse(entry.is_video())

    def test_folder_tree_recursive_totals(self):
        root = FolderNode("E:", "E:\\")
        child1 = root.get_or_create_child("photos", "E:\\photos\\")
        child1.direct_file_count = 5
        child1.direct_size_kb = 5000.0

        child2 = child1.get_or_create_child("summer", "E:\\photos\\summer\\")
        child2.direct_file_count = 3
        child2.direct_size_kb = 3000.0

        root.compute_recursive_totals()
        self.assertEqual(root.recursive_file_count, 8)
        self.assertEqual(root.recursive_size_kb, 8000.0)

    def test_data_store_filtering_and_sorting(self):
        store = DataStore()
        result = ParseResult()

        e1 = FileEntry(0, "apple.jpg", intern_folder("E:\\pics\\"), "jpg", 100.0, "Pictures", datetime(2021, 1, 1), 1)
        e2 = FileEntry(1, "banana.mp4", intern_folder("E:\\vids\\"), "mp4", 50000.0, "Videos", datetime(2021, 2, 1), 2)
        e3 = FileEntry(2, "apple.jpg", intern_folder("E:\\backup\\"), "jpg", 100.0, "Pictures", datetime(2021, 1, 1), 3)
        e4 = FileEntry(3, "عکس_زیبا.jpg", intern_folder("E:\\فارسی\\"), "jpg", 200.0, "Pictures", datetime(2021, 3, 1), 4)

        result.entries = [e1, e2, e3, e4]
        store.load_result(result, source_file="dummy.txt", root_remap="F:\\")

        # 1. Search filter (Persian query)
        filtered = store.filter_indices(search_query="زیبا")
        self.assertEqual(filtered, [3])

        # 2. Type filter
        vid_indices = store.filter_indices(selected_types='video')
        self.assertEqual(vid_indices, [1])

        # 3. Duplicate detection
        self.assertIn(("apple.jpg", 100.0), store.duplicates)
        self.assertEqual(store.duplicates[("apple.jpg", 100.0)], [0, 2])

        # 4. Root remap
        actual = store.get_actual_path(e1)
        self.assertEqual(actual, "F:\\pics\\apple.jpg")
        self.assertEqual(store.get_file_full_path(e1), "F:\\pics\\apple.jpg")

        # 5. Sorting
        sorted_by_size = store.sort_indices([0, 1, 2, 3], sort_key="size", reverse=True)
        self.assertEqual(sorted_by_size[0], 1)  # largest is banana.mp4


class TestServices(unittest.TestCase):
    """Test copy service, thumbnail service helpers, and availability check."""

    def test_windows_filename_sanitization(self):
        self.assertEqual(sanitize_windows_filename('photo<1>:test.jpg'), 'photo_1__test.jpg')
        self.assertEqual(sanitize_windows_filename('CON.txt'), '_CON.txt')
        self.assertEqual(sanitize_windows_filename('bad_trailing. . .'), 'bad_trailing')
        self.assertEqual(sanitize_windows_filename(''), 'unnamed')

    def test_subpath_detection(self):
        self.assertTrue(is_subpath("C:\\source", "C:\\source\\nested\\folder"))
        self.assertTrue(is_subpath("C:\\source", "C:\\source"))
        self.assertFalse(is_subpath("C:\\source", "D:\\dest"))
        self.assertFalse(is_subpath("C:\\source\\folder", "C:\\source"))

    def test_chunked_copy_and_dedup(self):
        """Test chunked file copy and flat copy deduplication."""
        with tempfile.TemporaryDirectory() as src_dir, tempfile.TemporaryDirectory() as dst_dir:
            file1 = os.path.join(src_dir, "test.txt")
            with open(file1, 'wb') as f:
                f.write(b"Hello Chunked Copy " * 1000)

            size_kb = os.path.getsize(file1) / 1024.0

            e1 = FileEntry(0, "test.txt", intern_folder(src_dir), "txt", size_kb, "Other", None, 1)
            # Duplicate entry with same name and size
            e2 = FileEntry(1, "test.txt", intern_folder(src_dir), "txt", size_kb, "Other", None, 2)

            thread = CopyThread(
                entries=[e1, e2],
                dest_dir=dst_dir,
                flat_copy=True,
                dedup_same_name_size=True
            )
            thread.run()

            dest_file = os.path.join(dst_dir, "test.txt")
            self.assertTrue(os.path.exists(dest_file))
            with open(dest_file, 'rb') as f:
                self.assertEqual(f.read(), b"Hello Chunked Copy " * 1000)

    def test_flat_copy_different_size_not_silently_skipped(self):
        """In flat copy, files with same name but different size must not be silently skipped."""
        with tempfile.TemporaryDirectory() as src1, tempfile.TemporaryDirectory() as src2, tempfile.TemporaryDirectory() as dst:
            file1 = os.path.join(src1, "report.pdf")
            with open(file1, 'wb') as f:
                f.write(b"Version 1" * 100)

            file2 = os.path.join(src2, "report.pdf")
            with open(file2, 'wb') as f:
                f.write(b"Version 2 - Much Larger" * 500)

            e1 = FileEntry(0, "report.pdf", intern_folder(src1), "pdf", os.path.getsize(file1) / 1024.0, "Other", None, 1)
            e2 = FileEntry(1, "report.pdf", intern_folder(src2), "pdf", os.path.getsize(file2) / 1024.0, "Other", None, 2)

            thread = CopyThread(
                entries=[e1, e2],
                dest_dir=dst,
                flat_copy=True,
                dedup_same_name_size=True
            )
            # Even if conflict action was SKIP, different size in flat copy must auto-rename and not be dropped!
            thread.set_conflict_action(ConflictAction.SKIP)
            thread.run()

            copied_files = os.listdir(dst)
            self.assertEqual(len(copied_files), 2, f"Both files must be kept, found: {copied_files}")
            self.assertIn("report.pdf", copied_files)
            self.assertIn("report (1).pdf", copied_files)

    def test_thumbnail_cache_and_long_paths(self):
        cache = ThumbnailCache(max_memory_mb=1)
        self.assertEqual(cache._max_memory, 1024 * 1024)

        norm = normalize_long_path("C:\\test\\path.jpg")
        if os.name == 'nt':
            self.assertTrue(norm.startswith('\\\\?\\'))

    def test_availability_check_scandir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            f1 = os.path.join(tmp_dir, "exists.png")
            with open(f1, 'w') as f:
                f.write("content")

            store = DataStore()
            e_avail = FileEntry(0, "exists.png", intern_folder(tmp_dir), "png", 1.0, "Pictures", None, 1)
            e_missing = FileEntry(1, "missing.png", intern_folder(tmp_dir), "png", 1.0, "Pictures", None, 2)

            res = ParseResult()
            res.entries = [e_avail, e_missing]
            store.load_result(res, source_file="dummy.txt")

            avail, unavail = check_availability_sync(store)
            self.assertEqual(avail, 1)
            self.assertEqual(unavail, 1)
            self.assertTrue(e_avail.is_available)
            self.assertFalse(e_missing.is_available)


class TestRealSystemAnalyzerFile(unittest.TestCase):
    """Smoke test against SystemAnalyzer.txt if present in workspace."""

    def test_parse_real_system_analyzer(self):
        possible_paths = [
            os.path.join(PROJECT_ROOT, "..", "SystemAnalyzer.txt"),
            os.path.join(PROJECT_ROOT, "SystemAnalyzer.txt"),
            "f:\\image\\SystemAnalyzer.txt"
        ]
        target_path = None
        for p in possible_paths:
            if os.path.isfile(p):
                target_path = os.path.abspath(p)
                break

        if not target_path:
            self.skipTest("SystemAnalyzer.txt not found in workspace.")

        enc = detect_file_encoding(target_path)
        self.assertEqual(enc, 'utf-16', "SystemAnalyzer.txt must be detected as utf-16")

        # Parse first 500 lines to verify no BOM in first entry
        result = parse_analyzer_file(target_path)
        self.assertGreater(len(result.entries), 0)
        first_entry = result.entries[0]
        self.assertFalse(
            first_entry.name.startswith('\ufeff'),
            f"First entry name starts with \\ufeff: {repr(first_entry.name)}"
        )
        self.assertEqual(first_entry.name, "IMG_20190822_144839_1.jpg")
        print(f"\n[Real File Check] Successfully parsed {len(result.entries):,} entries from SystemAnalyzer.txt")
        print(f"First entry: {first_entry.name} in {first_entry.folder} ({first_entry.size_display})")


class TestOffscreenRendering(unittest.TestCase):
    """
    Offscreen UI rendering test using widget.grab().
    Loads real or mock data into FileGridView and MainWindow, triggers full paint cycle
    including ThumbnailDelegate.paint(), and asserts that no AttributeError or paint exception occurs.
    """

    @classmethod
    def setUpClass(cls):
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(['-platform', 'offscreen'])

    def test_grid_view_grab_renders_delegates_without_error(self):
        from ui.file_grid_view import FileGridView
        from ui.file_grid_model import FileTableModel
        from services.thumbnail_service import ThumbnailService
        from PySide6.QtCore import QItemSelectionModel

        store = DataStore()
        res = ParseResult()

        real_file = None
        for p in [os.path.join(PROJECT_ROOT, "..", "SystemAnalyzer.txt"), "f:\\image\\SystemAnalyzer.txt"]:
            if os.path.isfile(p):
                real_file = os.path.abspath(p)
                break

        if real_file:
            parsed = parse_analyzer_file(real_file)
            res.entries = parsed.entries[:50]
        else:
            for i in range(20):
                res.entries.append(
                    FileEntry(i, f"image_{i}.jpg", intern_folder("C:\\photos\\"), "jpg", 150.0 * (i + 1), "Pictures", None, i + 1)
                )

        store.load_result(res, "test.txt")
        thumb_service = ThumbnailService(thumbnail_size=160)
        model = FileTableModel(store)
        model.set_indices(list(range(len(res.entries))))

        grid = FileGridView(thumb_service, cell_size=160)
        grid.set_model(model)
        grid.resize(800, 600)
        grid.show()

        # Select first item to trigger selection state rendering (QStyle.StateFlag.State_Selected)
        if grid._view.model().rowCount() > 0:
            grid._view.selectionModel().select(
                grid._view.model().index(0, 0),
                QItemSelectionModel.SelectionFlag.Select
            )

        # grab() invokes full painting cycle (paintEvent + ThumbnailDelegate.paint)
        try:
            pixmap = grid.grab()
        except Exception as e:
            self.fail(f"widget.grab() raised an exception during delegate painting: {e}")

        self.assertFalse(pixmap.isNull())
        self.assertGreater(pixmap.width(), 0)
        self.assertGreater(pixmap.height(), 0)
        print(f"\n[Offscreen UI Check] Rendered {len(res.entries)} items in FileGridView successfully via widget.grab() (size: {pixmap.width()}x{pixmap.height()})")

    def test_main_window_grab_and_state_save(self):
        from ui.main_window import MainWindow
        from core.settings import AppSettings
        from PySide6.QtWidgets import QToolBar

        settings = AppSettings()
        window = MainWindow(settings=settings)
        window.resize(1024, 768)
        window.show()

        # Verify toolbar objectName
        toolbar = window.findChild(QToolBar, "MainToolBar")
        self.assertIsNotNone(toolbar, "Toolbar must have objectName 'MainToolBar' for saveState() to work")

        try:
            pixmap = window.grab()
        except Exception as e:
            self.fail(f"MainWindow.grab() failed: {e}")

        self.assertFalse(pixmap.isNull())
        self.assertEqual(pixmap.width(), 1024)
        self.assertEqual(pixmap.height(), 768)
        print(f"[Offscreen UI Check] MainWindow rendered and grabbed cleanly (size: {pixmap.width()}x{pixmap.height()})")


if __name__ == "__main__":
    unittest.main(verbosity=2)

