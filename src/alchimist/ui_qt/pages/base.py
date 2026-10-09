"""Общая основа страниц."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from alchimist.services.app import AppService
from alchimist.ui_qt.bridge import ServiceBridge


class Page(QWidget):
    """Страница знает только о сервисах и мосте событий."""

    title: str = ""
    icon: str = ""
    #: Содержимое в области прокрутки. Нужно страницам, которым мало места по высоте:
    #: без прокрутки Qt сжимает их виджеты ниже нужного — списки и кнопки сплющиваются,
    #: текст обрезается. Так бывает на маленьком экране с большим масштабом и в
    #: тайловых оконных менеджерах, которые не дают окну его минимальный размер.
    scrollable: bool = False

    def __init__(
        self, app: AppService, bridge: ServiceBridge, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.app = app
        self.bridge = bridge
        host: QWidget = self
        if self.scrollable:
            area = QScrollArea()
            area.setWidgetResizable(True)  # места хватает — страница выглядит как без прокрутки
            area.setFrameShape(QFrame.Shape.NoFrame)
            host = QWidget()
            area.setWidget(host)
            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.addWidget(area)
        self._layout = QVBoxLayout(host)
        self._layout.setContentsMargins(16, 12, 16, 12)
        self._layout.setSpacing(8)
        self._dirty = True

    def layout_box(self) -> QVBoxLayout:
        return self._layout

    def invalidate(self, *_args) -> None:
        """Помечает страницу устаревшей: обновится, когда её покажут."""
        self._dirty = True
        if self.isVisible():
            self.refresh()

    def activate(self) -> None:
        if self._dirty:
            self.refresh()

    def refresh(self) -> None:
        self._dirty = False
