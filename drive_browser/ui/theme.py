"""
Theme definitions for dark and light modes.
Modern, premium aesthetic with carefully chosen color palettes.
"""

DARK_THEME = """
/* ─── Global ─── */
QWidget {
    background-color: #1a1a2e;
    color: #e0e0e0;
    font-family: "Segoe UI", "Tahoma", "Arial", sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #1a1a2e;
}

/* ─── Menu Bar ─── */
QMenuBar {
    background-color: #16213e;
    color: #e0e0e0;
    border-bottom: 1px solid #0f3460;
    padding: 2px;
}
QMenuBar::item:selected {
    background-color: #0f3460;
    border-radius: 4px;
}
QMenu {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item:selected {
    background-color: #0f3460;
    border-radius: 4px;
}
QMenu::separator {
    height: 1px;
    background-color: #0f3460;
    margin: 4px 8px;
}

/* ─── Tool Bar ─── */
QToolBar {
    background-color: #16213e;
    border-bottom: 1px solid #0f3460;
    padding: 4px;
    spacing: 6px;
}
QToolButton {
    background-color: transparent;
    color: #e0e0e0;
    border: none;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
}
QToolButton:hover {
    background-color: #0f3460;
}
QToolButton:pressed {
    background-color: #533483;
}
QToolButton:checked {
    background-color: #533483;
    color: #ffffff;
}

/* ─── Splitter ─── */
QSplitter::handle {
    background-color: #0f3460;
    width: 2px;
    height: 2px;
}
QSplitter::handle:hover {
    background-color: #e94560;
}

/* ─── Tree View ─── */
QTreeView {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 8px;
    padding: 4px;
    outline: none;
}
QTreeView::item {
    padding: 4px 6px;
    border-radius: 4px;
}
QTreeView::item:selected {
    background-color: #533483;
    color: #ffffff;
}
QTreeView::item:hover {
    background-color: #0f3460;
}
QTreeView::branch {
    background-color: transparent;
}

/* ─── Table View ─── */
QTableView, QListView {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 8px;
    gridline-color: #0f3460;
    outline: none;
}
QTableView::item, QListView::item {
    padding: 4px;
}
QTableView::item:selected, QListView::item:selected {
    background-color: #533483;
    color: #ffffff;
}
QTableView::item:hover, QListView::item:hover {
    background-color: rgba(83, 52, 131, 0.3);
}
QHeaderView::section {
    background-color: #0f3460;
    color: #e0e0e0;
    border: none;
    border-right: 1px solid #16213e;
    padding: 6px 8px;
    font-weight: bold;
}
QHeaderView::section:hover {
    background-color: #533483;
}

/* ─── Scroll Bars ─── */
QScrollBar:vertical {
    background-color: #16213e;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background-color: #0f3460;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #533483;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background-color: #16213e;
    height: 10px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background-color: #0f3460;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #533483;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ─── Input Fields ─── */
QLineEdit {
    background-color: #0f3460;
    color: #e0e0e0;
    border: 1px solid #533483;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #e94560;
}
QLineEdit:focus {
    border-color: #e94560;
}

QComboBox {
    background-color: #0f3460;
    color: #e0e0e0;
    border: 1px solid #533483;
    border-radius: 6px;
    padding: 4px 10px;
    min-width: 80px;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid #e0e0e0;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    selection-background-color: #533483;
    border-radius: 6px;
}

QSpinBox, QDoubleSpinBox {
    background-color: #0f3460;
    color: #e0e0e0;
    border: 1px solid #533483;
    border-radius: 6px;
    padding: 4px 8px;
}

/* ─── Buttons ─── */
QPushButton {
    background-color: #533483;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #e94560;
}
QPushButton:pressed {
    background-color: #c23152;
}
QPushButton:disabled {
    background-color: #2a2a4a;
    color: #666;
}

/* ─── Progress Bar ─── */
QProgressBar {
    background-color: #0f3460;
    border: none;
    border-radius: 6px;
    text-align: center;
    color: #ffffff;
    height: 20px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #533483, stop:1 #e94560);
    border-radius: 6px;
}

/* ─── Status Bar ─── */
QStatusBar {
    background-color: #16213e;
    color: #e0e0e0;
    border-top: 1px solid #0f3460;
    padding: 2px;
}

/* ─── Tab Widget ─── */
QTabWidget::pane {
    border: 1px solid #0f3460;
    border-radius: 6px;
    background-color: #16213e;
}
QTabBar::tab {
    background-color: #0f3460;
    color: #e0e0e0;
    border: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 16px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #533483;
    color: #ffffff;
}
QTabBar::tab:hover {
    background-color: rgba(83, 52, 131, 0.5);
}

/* ─── Group Box ─── */
QGroupBox {
    border: 1px solid #0f3460;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #e94560;
}

/* ─── Check Box & Radio ─── */
QCheckBox, QRadioButton {
    color: #e0e0e0;
    spacing: 6px;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #533483;
    border-radius: 4px;
    background-color: #0f3460;
}
QRadioButton::indicator {
    border-radius: 9px;
}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: #e94560;
    border-color: #e94560;
}

/* ─── Slider ─── */
QSlider::groove:horizontal {
    background-color: #0f3460;
    height: 6px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background-color: #e94560;
    width: 16px;
    height: 16px;
    border-radius: 8px;
    margin: -5px 0;
}
QSlider::handle:horizontal:hover {
    background-color: #ff6b81;
}

/* ─── Dialog ─── */
QDialog {
    background-color: #1a1a2e;
}

/* ─── Label ─── */
QLabel {
    color: #e0e0e0;
}

/* ─── ToolTip ─── */
QToolTip {
    background-color: #0f3460;
    color: #e0e0e0;
    border: 1px solid #533483;
    border-radius: 4px;
    padding: 4px 8px;
}
"""

LIGHT_THEME = """
/* ─── Global ─── */
QWidget {
    background-color: #f5f5f7;
    color: #2d2d2d;
    font-family: "Segoe UI", "Tahoma", "Arial", sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #f5f5f7;
}

/* ─── Menu Bar ─── */
QMenuBar {
    background-color: #ffffff;
    color: #2d2d2d;
    border-bottom: 1px solid #e0e0e4;
    padding: 2px;
}
QMenuBar::item:selected {
    background-color: #e8e8ed;
    border-radius: 4px;
}
QMenu {
    background-color: #ffffff;
    color: #2d2d2d;
    border: 1px solid #e0e0e4;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item:selected {
    background-color: #0071e3;
    color: #ffffff;
    border-radius: 4px;
}

/* ─── Tool Bar ─── */
QToolBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e0e0e4;
    padding: 4px;
    spacing: 6px;
}
QToolButton {
    background-color: transparent;
    color: #2d2d2d;
    border: none;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
}
QToolButton:hover {
    background-color: #e8e8ed;
}
QToolButton:pressed, QToolButton:checked {
    background-color: #0071e3;
    color: #ffffff;
}

/* ─── Splitter ─── */
QSplitter::handle {
    background-color: #e0e0e4;
    width: 2px;
    height: 2px;
}

/* ─── Tree View ─── */
QTreeView {
    background-color: #ffffff;
    color: #2d2d2d;
    border: 1px solid #e0e0e4;
    border-radius: 8px;
    padding: 4px;
    outline: none;
}
QTreeView::item {
    padding: 4px 6px;
    border-radius: 4px;
}
QTreeView::item:selected {
    background-color: #0071e3;
    color: #ffffff;
}
QTreeView::item:hover {
    background-color: #e8e8ed;
}

/* ─── Table View ─── */
QTableView, QListView {
    background-color: #ffffff;
    color: #2d2d2d;
    border: 1px solid #e0e0e4;
    border-radius: 8px;
    gridline-color: #f0f0f2;
    outline: none;
}
QTableView::item:selected, QListView::item:selected {
    background-color: #0071e3;
    color: #ffffff;
}
QTableView::item:hover, QListView::item:hover {
    background-color: rgba(0, 113, 227, 0.1);
}
QHeaderView::section {
    background-color: #f5f5f7;
    color: #2d2d2d;
    border: none;
    border-right: 1px solid #e0e0e4;
    padding: 6px 8px;
    font-weight: bold;
}

/* ─── Scroll Bars ─── */
QScrollBar:vertical {
    background-color: #f5f5f7;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background-color: #c0c0c4;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #0071e3;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background-color: #f5f5f7;
    height: 10px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background-color: #c0c0c4;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #0071e3;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ─── Input Fields ─── */
QLineEdit {
    background-color: #ffffff;
    color: #2d2d2d;
    border: 1px solid #c0c0c4;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #0071e3;
}
QLineEdit:focus {
    border-color: #0071e3;
}

QComboBox {
    background-color: #ffffff;
    color: #2d2d2d;
    border: 1px solid #c0c0c4;
    border-radius: 6px;
    padding: 4px 10px;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid #666;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    border: 1px solid #e0e0e4;
    selection-background-color: #0071e3;
    selection-color: #ffffff;
}

QSpinBox, QDoubleSpinBox {
    background-color: #ffffff;
    color: #2d2d2d;
    border: 1px solid #c0c0c4;
    border-radius: 6px;
    padding: 4px 8px;
}

/* ─── Buttons ─── */
QPushButton {
    background-color: #0071e3;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #0077ed;
}
QPushButton:pressed {
    background-color: #005bb5;
}
QPushButton:disabled {
    background-color: #c0c0c4;
    color: #999;
}

/* ─── Progress Bar ─── */
QProgressBar {
    background-color: #e0e0e4;
    border: none;
    border-radius: 6px;
    text-align: center;
    height: 20px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #0071e3, stop:1 #34c759);
    border-radius: 6px;
}

/* ─── Status Bar ─── */
QStatusBar {
    background-color: #ffffff;
    color: #2d2d2d;
    border-top: 1px solid #e0e0e4;
}

/* ─── Tab Widget ─── */
QTabWidget::pane {
    border: 1px solid #e0e0e4;
    border-radius: 6px;
    background-color: #ffffff;
}
QTabBar::tab {
    background-color: #e8e8ed;
    color: #2d2d2d;
    border: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 16px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #0071e3;
    color: #ffffff;
}

/* ─── Group Box ─── */
QGroupBox {
    border: 1px solid #e0e0e4;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #0071e3;
}

/* ─── Check Box & Radio ─── */
QCheckBox::indicator, QRadioButton::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #c0c0c4;
    border-radius: 4px;
    background-color: #ffffff;
}
QRadioButton::indicator {
    border-radius: 9px;
}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: #0071e3;
    border-color: #0071e3;
}

/* ─── Slider ─── */
QSlider::groove:horizontal {
    background-color: #e0e0e4;
    height: 6px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background-color: #0071e3;
    width: 16px;
    height: 16px;
    border-radius: 8px;
    margin: -5px 0;
}

/* ─── Dialog ─── */
QDialog {
    background-color: #f5f5f7;
}

/* ─── ToolTip ─── */
QToolTip {
    background-color: #2d2d2d;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 4px 8px;
}
"""


def get_theme(dark: bool = True) -> str:
    """Get the stylesheet for the specified theme."""
    return DARK_THEME if dark else LIGHT_THEME


def apply_theme(app, dark: bool = True):
    """Apply the theme stylesheet to the given QApplication or QWidget."""
    app.setStyleSheet(get_theme(dark))
