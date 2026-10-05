"""Значок элемента и строка значков (02 §6)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from alchimist.core.elements import Element, ElementVector
from alchimist.ui_qt.theme import element_color, rarity_color, readable_text_color

BADGE_SIZE = 18


def badge_pixmap(element: Element, count: int = 1, size: int = BADGE_SIZE) -> QPixmap:
    """Кружок цвета стихии с числом внутри."""
    ratio = 2
    pixmap = QPixmap(size * ratio, size * ratio)
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = element_color(element)
    painter.setBrush(color)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QRectF(0.5, 0.5, size - 1, size - 1))

    if count > 1:
        painter.setPen(readable_text_color(color))
        font = QFont(painter.font())
        font.setPointSizeF(size * 0.5)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, str(count))
    painter.end()
    return pixmap


class ElementBadges(QWidget):
    """Строка значков: по одному на каждый ненулевой элемент."""

    def __init__(self, vector: ElementVector | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vector = vector or ElementVector()
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(BADGE_SIZE + 4)
        self._update_tooltip()

    def set_vector(self, vector: ElementVector) -> None:
        self._vector = vector
        self._update_tooltip()
        self.updateGeometry()
        self.update()

    def _update_tooltip(self) -> None:
        self.setToolTip(self._vector.format_ru())

    def sizeHint(self) -> QSize:
        count = sum(1 for _ in self._vector.items())
        return QSize(max(1, count) * (BADGE_SIZE + 3), BADGE_SIZE + 4)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        x = 0
        for element, count in self._vector.items():
            painter.drawPixmap(x, 2, badge_pixmap(element, count))
            x += BADGE_SIZE + 3
        painter.end()


def rarity_icon(rarity) -> QIcon:
    """Точка цвета редкости: название остаётся читаемым, метка всё равно видна."""
    return QIcon(colored_dot(rarity_color(rarity), 9))


def colored_dot(color: QColor, size: int = 10) -> QPixmap:
    ratio = 2
    pixmap = QPixmap(size * ratio, size * ratio)
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(color)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QRectF(0.5, 0.5, size - 1, size - 1))
    painter.end()
    return pixmap
