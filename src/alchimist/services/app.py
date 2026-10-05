"""Сборка приложения: один объект, через который работает интерфейс (NFR-1)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alchimist.core.errors import Message
from alchimist.core.models import Ingredient, Potion
from alchimist.services.brewing import BrewingService
from alchimist.services.catalog import CatalogService
from alchimist.services.distilling import DistillingService
from alchimist.services.events import EventBus, SettingsChanged
from alchimist.services.exchange import ExchangeService
from alchimist.services.inventory import InventoryService
from alchimist.services.journal import JournalService
from alchimist.services.queue import QueueService
from alchimist.services.settings import SettingsService
from alchimist.storage.json_store import (
    JsonCatalogRepository,
    JsonInventoryRepository,
    JsonJournalRepository,
    JsonQueueRepository,
)
from alchimist.storage.paths import Paths
from alchimist.storage.settings_store import SettingsStore


@dataclass(slots=True)
class AppService:
    """Фасад: интерфейс держит один такой объект и подписывается на его шину."""

    paths: Paths
    bus: EventBus
    settings: SettingsService
    catalog: CatalogService
    inventory: InventoryService
    journal: JournalService
    queue: QueueService
    brewing: BrewingService
    distilling: DistillingService
    exchange: ExchangeService

    def __post_init__(self) -> None:
        self.bus.subscribe(SettingsChanged, self._on_settings)
        self._on_settings(SettingsChanged())

    def _on_settings(self, _event) -> None:
        self.brewing.set_kits(self.settings.kits)

    # ── общие мелочи для интерфейса ───────────────────────────────────────
    @property
    def startup_notices(self) -> list[Message]:
        """Что пошло не так при загрузке файлов (NFR-8)."""
        return [
            *self.catalog.notices,
            *self.inventory.notices,
            *self.journal.notices,
            *self.queue.notices,
        ]

    def can_delete_ingredient(self, ingredient_id: str) -> bool:
        """FR-1.5: удалять можно только то, чего нет ни в инвентаре, ни в журнале."""
        return not (
            self.inventory.is_ingredient_used(ingredient_id)
            or self.journal.uses_ingredient(ingredient_id)
        )

    def can_delete_potion(self, potion_id: str) -> bool:
        return not (self.inventory.is_potion_used(potion_id) or self.journal.uses_potion(potion_id))

    def delete_ingredient(self, ingredient_id: str) -> None:
        self.catalog.delete_ingredient(
            ingredient_id, used=not self.can_delete_ingredient(ingredient_id)
        )
        self.brewing.invalidate()

    def delete_potion(self, potion_id: str) -> None:
        self.catalog.delete_potion(potion_id, used=not self.can_delete_potion(potion_id))
        self.brewing.invalidate()

    def add_ingredient(self, ingredient: Ingredient) -> tuple[Ingredient, list[Message]]:
        result = self.catalog.add_ingredient(ingredient)
        self.brewing.invalidate()
        return result

    def update_ingredient(self, ingredient: Ingredient) -> tuple[Ingredient, list[Message]]:
        result = self.catalog.update_ingredient(ingredient)
        self.brewing.invalidate()
        return result

    def add_potion(self, potion: Potion) -> tuple[Potion, list[Message]]:
        result = self.catalog.add_potion(potion)
        self.brewing.invalidate()
        return result

    def update_potion(self, potion: Potion) -> tuple[Potion, list[Message]]:
        result = self.catalog.update_potion(potion)
        self.brewing.invalidate()
        return result

    def set_recipe(self, potion_id: str, recipe) -> tuple[Potion, list[Message]]:
        result = self.catalog.set_recipe(potion_id, recipe)
        self.brewing.invalidate()
        return result

    def reload(self) -> None:
        self.catalog.reload()
        self.inventory.reload()
        self.journal.reload()
        self.queue.reload()
        self.settings.reload()
        self.brewing.set_kits(self.settings.kits)


def build_app(root: Path | None = None, profile: str | None = None) -> AppService:
    """Собирает сервисы поверх JSON-хранилища."""
    paths = Paths.at(root) if root is not None else Paths.resolve()
    settings_store = SettingsStore(paths)
    loaded = settings_store.load()
    paths = paths.for_profile(profile or loaded.active_profile)
    settings_store = SettingsStore(paths)
    paths.ensure()

    bus = EventBus()
    settings = SettingsService(settings_store, bus)
    catalog = CatalogService(JsonCatalogRepository(paths), bus)
    inventory = InventoryService(JsonInventoryRepository(paths), bus)
    journal = JournalService(JsonJournalRepository(paths), bus)
    queue = QueueService(JsonQueueRepository(paths), bus)
    brewing = BrewingService(catalog, inventory, journal, bus, queue, settings.kits)
    distilling = DistillingService(catalog, inventory, journal, bus)
    exchange = ExchangeService(catalog)

    # Любое изменение справочника или инвентаря сбрасывает кэш подбора (FR-5.5).
    from alchimist.services.events import CatalogChanged, InventoryChanged, QueueChanged

    bus.subscribe(CatalogChanged, lambda _e: brewing.invalidate())
    bus.subscribe(InventoryChanged, lambda _e: brewing.invalidate())
    # Очередь занимает реагенты, поэтому её правка тоже меняет подбор (FR-12.2).
    bus.subscribe(QueueChanged, lambda _e: brewing.invalidate())

    return AppService(
        paths, bus, settings, catalog, inventory, journal, queue, brewing, distilling, exchange
    )
