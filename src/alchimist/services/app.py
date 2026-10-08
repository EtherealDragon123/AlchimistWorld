"""Сборка приложения: один объект, через который работает интерфейс (NFR-1)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from alchimist.core.errors import AlchimistError, ErrorCode, Message
from alchimist.core.models import Character, Ingredient, Kit, Potion
from alchimist.data import BUILTIN_CATALOG
from alchimist.services.brewing import BrewingService
from alchimist.services.catalog import CatalogService
from alchimist.services.characters import CharacterService
from alchimist.services.distilling import DistillingService
from alchimist.services.events import (
    CatalogChanged,
    CharacterChanged,
    EventBus,
    InventoryChanged,
    JournalChanged,
    QueueChanged,
)
from alchimist.services.exchange import ExchangeService, MergeChoice
from alchimist.services.inventory import InventoryService
from alchimist.services.journal import JournalService
from alchimist.services.queue import QueueService
from alchimist.services.settings import SettingsService
from alchimist.storage.character_store import CharacterStore
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
    characters: CharacterService

    def __post_init__(self) -> None:
        # Подбор смотрит глазами активного персонажа: его рецепты, его наборы.
        self.catalog.known_recipes = self.characters.known_recipe_ids
        self.bus.subscribe(CharacterChanged, self._on_character)
        self._on_character(CharacterChanged())

    def _on_character(self, _event) -> None:
        self.brewing.set_kits(self.characters.kits)

    # ── общие мелочи для интерфейса ───────────────────────────────────────
    @property
    def startup_notices(self) -> list[Message]:
        """Что пошло не так при загрузке файлов (NFR-8)."""
        return [
            *self.catalog.notices,
            *self.characters.notices,
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

    # ── правка справочника: только GM (FR-14.6) ───────────────────────────
    @property
    def can_edit_catalog(self) -> bool:
        return self.characters.can_edit_catalog()

    def _require_gm(self) -> None:
        if not self.can_edit_catalog:
            raise AlchimistError(ErrorCode.GM_ONLY)

    def delete_ingredient(self, ingredient_id: str) -> None:
        self._require_gm()
        self.catalog.delete_ingredient(
            ingredient_id, used=not self.can_delete_ingredient(ingredient_id)
        )
        self.brewing.invalidate()

    def delete_potion(self, potion_id: str) -> None:
        self._require_gm()
        self.catalog.delete_potion(potion_id, used=not self.can_delete_potion(potion_id))
        self.brewing.invalidate()

    def add_ingredient(self, ingredient: Ingredient) -> tuple[Ingredient, list[Message]]:
        self._require_gm()
        result = self.catalog.add_ingredient(ingredient)
        self.brewing.invalidate()
        return result

    def update_ingredient(self, ingredient: Ingredient) -> tuple[Ingredient, list[Message]]:
        self._require_gm()
        result = self.catalog.update_ingredient(ingredient)
        self.brewing.invalidate()
        return result

    def set_ingredient_hidden(self, ingredient_id: str, hidden: bool) -> Ingredient:
        self._require_gm()
        return self.catalog.set_ingredient_hidden(ingredient_id, hidden)

    def add_potion(self, potion: Potion) -> tuple[Potion, list[Message]]:
        self._require_gm()
        result = self.catalog.add_potion(potion)
        self.brewing.invalidate()
        return result

    def update_potion(self, potion: Potion) -> tuple[Potion, list[Message]]:
        self._require_gm()
        result = self.catalog.update_potion(potion)
        self.brewing.invalidate()
        return result

    def set_potion_hidden(self, potion_id: str, hidden: bool) -> Potion:
        self._require_gm()
        return self.catalog.set_potion_hidden(potion_id, hidden)

    def set_recipe(self, potion_id: str, recipe) -> tuple[Potion, list[Message]]:
        self._require_gm()
        result = self.catalog.set_recipe(potion_id, recipe)
        self.brewing.invalidate()
        return result

    def save_as_recipe(
        self, entry_id: str, potion_id: str | None = None
    ) -> tuple[Potion, list[Message]]:
        """П-7.5: комбинация из журнала становится рецептом — это правка справочника."""
        self._require_gm()
        return self.brewing.save_as_recipe(entry_id, potion_id)

    def export_catalog(self, path: Path) -> Path:
        """FR-10.2: выгружает GM. Игроку нечего отдавать: там все рецепты разом."""
        self._require_gm()
        active = self.characters.active
        return self.exchange.export(path, active.name if active else "")

    # ── персонажи (FR-14.x) ───────────────────────────────────────────────
    def seed_catalog(self) -> list[Message]:
        """FR-14.2: дополняет справочник встроенным. Своё не трогает, только новое."""
        if not BUILTIN_CATALOG.exists():
            return []
        plan = self.exchange.plan(BUILTIN_CATALOG)
        if not plan.added:
            return []
        messages = self.exchange.apply(plan, default=MergeChoice.KEEP_MINE)
        self.brewing.invalidate()
        return messages

    def create_character(
        self,
        name: str,
        kits: Iterable[Kit] = (),
        *,
        known: Iterable[str] | None = None,
        seed_catalog: bool = True,
    ) -> Character:
        """Создаёт персонажа и сразу переключается на него.

        Сначала справочник дополняется встроенным: стартовые рецепты новичка
        считаются уже по нему. Имя GM добавляет встроенного GM, а если он уже
        есть — просто переключает на него.
        """
        if seed_catalog:
            self.seed_catalog()
        character = self.characters.create(name, kits, known=known)
        self.switch_character(character.id)
        return character

    def switch_character(self, character_id: str) -> Character:
        """FR-14.5: другой персонаж — другие инвентарь, журнал и очередь."""
        character = self.characters.get(character_id)
        self.characters.activate(character_id)
        if self.settings.settings.active_profile != character_id:
            self.settings.set_active_profile(character_id)
        self._bind_profile(character_id)
        self.brewing.set_kits(character.kits)
        self.bus.publish(CharacterChanged(switched=True))
        self.bus.publish(InventoryChanged())
        self.bus.publish(JournalChanged())
        self.bus.publish(QueueChanged())
        return character

    def _bind_profile(self, profile: str) -> None:
        """Перецепляет файлы профиля на другого персонажа и перечитывает их."""
        self.paths = self.paths.for_profile(profile)
        self.inventory.repo = JsonInventoryRepository(self.paths)
        self.journal.repo = JsonJournalRepository(self.paths)
        self.queue.repo = JsonQueueRepository(self.paths)
        self.inventory.reload()
        self.journal.reload()
        self.queue.reload()
        self.brewing.invalidate()

    def rename_character(self, character_id: str, name: str) -> Character:
        return self.characters.rename(character_id, name)

    def delete_character(self, character_id: str) -> None:
        """Активного сначала сменяем на другого: без персонажа окно не живёт."""
        self.characters.get(character_id)
        if len(self.characters.characters()) <= 1:
            raise AlchimistError(ErrorCode.LAST_CHARACTER)
        active = self.characters.active
        if active is not None and active.id == character_id:
            others = [c for c in self.characters.characters() if c.id != character_id]
            self.switch_character(others[0].id)
        self.characters.delete(character_id)
        self.bus.publish(CharacterChanged())

    def set_kits(self, kits: Iterable[Kit]) -> Character:
        return self.characters.set_kits(kits)

    def learn_recipe(self, potion_id: str) -> Character:
        return self.characters.learn(potion_id)

    def forget_recipe(self, potion_id: str) -> Character:
        return self.characters.forget(potion_id)

    def reload(self) -> None:
        self.catalog.reload()
        self.characters.reload()
        self.inventory.reload()
        self.journal.reload()
        self.queue.reload()
        self.settings.reload()
        self.brewing.set_kits(self.characters.kits)


def build_app(root: Path | None = None, profile: str | None = None) -> AppService:
    """Собирает сервисы поверх JSON-хранилища.

    `profile` задаёт папку профиля явно (консоль, `--profile`). Иначе открывается
    персонаж, с которым закрылись в прошлый раз, или первый по списку.
    """
    paths = Paths.at(root) if root is not None else Paths.resolve()
    bus = EventBus()
    settings = SettingsService(SettingsStore(paths), bus)
    catalog = CatalogService(JsonCatalogRepository(paths), bus)
    characters = CharacterService(CharacterStore(paths), catalog, bus)
    # Профиль из версии без персонажей становится персонажем до первой записи
    # settings.toml: только там ещё лежат старые имя и наборы (03 §6.12).
    characters.migrate_legacy(settings.settings)

    if profile is not None:
        active = profile if profile in {c.id for c in characters.characters()} else None
    else:
        active = characters.resolve_active(settings.settings.active_profile)
    characters.activate(active)
    paths = paths.for_profile(profile or active or settings.settings.active_profile)
    paths.ensure(profile=active is not None or profile is not None)
    if profile is None and active is not None and settings.settings.active_profile != active:
        settings.set_active_profile(active)

    inventory = InventoryService(JsonInventoryRepository(paths), bus)
    journal = JournalService(JsonJournalRepository(paths), bus)
    queue = QueueService(JsonQueueRepository(paths), bus)
    brewing = BrewingService(catalog, inventory, journal, bus, queue, characters.kits)
    distilling = DistillingService(catalog, inventory, journal, bus)
    exchange = ExchangeService(catalog)

    # Любое изменение справочника, инвентаря или знаний сбрасывает кэш подбора (FR-5.5).
    bus.subscribe(CatalogChanged, lambda _e: brewing.invalidate())
    bus.subscribe(InventoryChanged, lambda _e: brewing.invalidate())
    bus.subscribe(CharacterChanged, lambda _e: brewing.invalidate())
    # Очередь занимает реагенты, поэтому её правка тоже меняет подбор (FR-12.2).
    bus.subscribe(QueueChanged, lambda _e: brewing.invalidate())

    return AppService(
        paths,
        bus,
        settings,
        catalog,
        inventory,
        journal,
        queue,
        brewing,
        distilling,
        exchange,
        characters,
    )
