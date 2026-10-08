"""Мост: события сервисов → Qt-сигналы (03 §2)."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from alchimist.services.events import (
    CatalogChanged,
    CharacterChanged,
    EventBus,
    InventoryChanged,
    JournalChanged,
    QueueChanged,
    SettingsChanged,
)


class ServiceBridge(QObject):
    """Тонкая прослойка: сервисы ничего не знают о Qt, страницы — о шине."""

    catalog_changed = Signal(object)
    inventory_changed = Signal(object)
    journal_changed = Signal(object)
    queue_changed = Signal(object)
    settings_changed = Signal(object)
    character_changed = Signal(object)

    def __init__(self, bus: EventBus, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._bus = bus
        self._unsubscribe = [
            bus.subscribe(CatalogChanged, self.catalog_changed.emit),
            bus.subscribe(InventoryChanged, self.inventory_changed.emit),
            bus.subscribe(JournalChanged, self.journal_changed.emit),
            bus.subscribe(QueueChanged, self.queue_changed.emit),
            bus.subscribe(SettingsChanged, self.settings_changed.emit),
            bus.subscribe(CharacterChanged, self.character_changed.emit),
        ]

    def disconnect_bus(self) -> None:
        for off in self._unsubscribe:
            off()
        self._unsubscribe.clear()
