"""Общая основа страниц."""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from alchimist.services.app import AppService
from alchimist.ui_qt.bridge import ServiceBridge


class Page(QWidget):
    """Страница знает только о сервисах и мосте событий."""

    title: str = ""
    icon: str = ""

    def __init__(
        self, app: AppService, bridge: ServiceBridge, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.app = app
        self.bridge = bridge
        self._layout = QVBoxLayout(self)
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
