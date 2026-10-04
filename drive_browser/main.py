"""
Drive Content Browser — Main Application Entry Point
High-performance virtualized drive content browser with Persian language support,
lazy thumbnail generation, and zero file duplication.
"""
from __future__ import annotations

import sys
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from core.settings import AppSettings
from ui.theme import apply_theme
from ui.main_window import MainWindow


def main():
    # Enable High DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName(AppSettings.APPLICATION)
    app.setOrganizationName(AppSettings.ORGANIZATION)

    # Set up global font with Persian / Arabic script support
    font = QFont("Segoe UI", 10)
    font.setStyleHint(QFont.SansSerif)
    app.setFont(font)

    # Load persistent settings
    settings = AppSettings()
    apply_theme(app, settings.theme == "dark")

    # Initialize main window
    initial_file = sys.argv[1] if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]) else None
    window = MainWindow(settings=settings, initial_file=initial_file)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
