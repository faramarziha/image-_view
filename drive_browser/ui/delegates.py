"""
Custom item delegates for thumbnail grid view.
Renders thumbnails with file info overlay, handles lazy loading.
"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, QSize, QRect, QModelIndex, QRectF
from PySide6.QtGui import (
    QPainter, QPixmap, QColor, QFont, QFontMetrics, QPen, QBrush,
    QLinearGradient, QPainterPath,
)
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QWidget

from services.thumbnail_service import ThumbnailService


class ThumbnailDelegate(QStyledItemDelegate):
    """
    Custom delegate that renders thumbnails with file info for grid view.
    Requests thumbnails lazily from the ThumbnailService.
    """

    def __init__(self, thumbnail_service: ThumbnailService, cell_size: int = 200, parent=None):
        super().__init__(parent)
        self._thumb_service = thumbnail_service
        self._cell_size = cell_size
        self._placeholder_pixmap: Optional[QPixmap] = None
        self._error_pixmap: Optional[QPixmap] = None

    @property
    def cell_size(self) -> int:
        return self._cell_size

    @cell_size.setter
    def cell_size(self, size: int):
        self._cell_size = max(80, min(400, size))

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(self._cell_size, self._cell_size + 32)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        rect = option.rect
        is_selected = option.state & QStyleOptionViewItem.State_Selected
        is_hovered = option.state & QStyleOptionViewItem.State_MouseOver

        # Background
        if is_selected:
            bg_color = QColor("#533483")
        elif is_hovered:
            bg_color = QColor(83, 52, 131, 50)
        else:
            bg_color = QColor(0, 0, 0, 0)

        # Draw rounded background
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), 8, 8)
        painter.fillPath(path, bg_color)

        # Thumbnail area
        thumb_margin = 6
        thumb_rect = QRect(
            rect.x() + thumb_margin,
            rect.y() + thumb_margin,
            rect.width() - 2 * thumb_margin,
            rect.width() - 2 * thumb_margin,  # Square
        )

        # Get file path and request thumbnail
        file_path = index.data(Qt.UserRole)
        pixmap = None
        if file_path:
            pixmap = self._thumb_service.request_thumbnail(file_path)

        if pixmap and not pixmap.isNull():
            # Draw thumbnail centered in thumb_rect
            scaled = pixmap.scaled(
                thumb_rect.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            x = thumb_rect.x() + (thumb_rect.width() - scaled.width()) // 2
            y = thumb_rect.y() + (thumb_rect.height() - scaled.height()) // 2

            # Draw shadow effect
            shadow_rect = QRect(x + 2, y + 2, scaled.width(), scaled.height())
            painter.fillRect(shadow_rect, QColor(0, 0, 0, 40))

            painter.drawPixmap(x, y, scaled)
        else:
            # Draw placeholder
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(40, 40, 60, 100))
            path = QPainterPath()
            path.addRoundedRect(QRectF(thumb_rect), 6, 6)
            painter.drawPath(path)

            # File extension icon
            entry = index.data(Qt.UserRole + 2)
            if entry:
                ext_text = entry.extension.upper()
                if not os.path.isfile(file_path or ''):
                    ext_text = "⚠"
            else:
                ext_text = "?"

            painter.setPen(QColor(150, 150, 170))
            font = QFont("Segoe UI", 16, QFont.Bold)
            painter.setFont(font)
            painter.drawText(thumb_rect, Qt.AlignCenter, ext_text)

        # File name text below thumbnail
        text_rect = QRect(
            rect.x() + 4,
            thumb_rect.bottom() + 2,
            rect.width() - 8,
            28,
        )

        entry = index.data(Qt.UserRole + 2)
        if entry:
            name = entry.name
            # Draw name
            painter.setPen(QColor("#e0e0e0") if not is_selected else QColor("#ffffff"))
            font = QFont("Segoe UI", 9)
            painter.setFont(font)
            fm = QFontMetrics(font)
            elided = fm.elidedText(name, Qt.ElideMiddle, text_rect.width())
            painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, elided)

            # Draw size in small text
            size_rect = QRect(text_rect.x(), text_rect.y() + 14, text_rect.width(), 14)
            painter.setPen(QColor(150, 150, 170))
            font.setPointSize(8)
            painter.setFont(font)
            painter.drawText(size_rect, Qt.AlignHCenter | Qt.AlignTop, entry.size_display)

        painter.restore()
