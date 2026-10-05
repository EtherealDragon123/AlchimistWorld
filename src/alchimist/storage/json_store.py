"""Реализация репозиториев на JSON-файлах (03 §6)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alchimist.core.errors import ErrorCode, Message, StorageError, WarningCode, warning
from alchimist.core.models import (
    BrewQueue,
    Catalog,
    Ingredient,
    Inventory,
    JournalEntry,
    Potion,
)
from alchimist.storage.atomic import PendingWrite, backup_path, commit_all, prepare_write
from alchimist.storage.migrations import CURRENT_VERSIONS, load_json
from alchimist.storage.paths import Paths
from alchimist.storage.serde import (
    dumps,
    entry_from_dict,
    entry_to_dict,
    ingredient_from_dict,
    ingredient_to_dict,
    inventory_from_dict,
    inventory_to_dict,
    potion_from_dict,
    potion_to_dict,
    queue_from_dict,
    queue_to_dict,
)


def _read(path: Path, kind: str, notices: list[Message]) -> dict[str, Any] | None:
    """Читает файл, при поломке пробует `.bak` (NFR-8)."""
    if not path.exists():
        return None
    try:
        return load_json(path, kind)
    except StorageError:
        backup = backup_path(path)
        if not backup.exists():
            raise
        data = load_json(backup, kind)
        notices.append(
            warning(WarningCode.STORAGE_RECOVERED_FROM_BAK, path=str(path), backup=str(backup))
        )
        return data


@dataclass(slots=True)
class JsonCatalogRepository:
    """`catalog/ingredients.json` и `catalog/potions.json` (03 §6.3–6.4)."""

    paths: Paths
    notices: list[Message] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.notices is None:
            self.notices = []

    def load(self) -> Catalog:
        self.notices.clear()
        ingredients: list[Ingredient] = []
        potions: list[Potion] = []

        data = _read(self.paths.ingredients_file, "ingredients", self.notices)
        if data:
            path = str(self.paths.ingredients_file)
            ingredients = [ingredient_from_dict(d, path) for d in data.get("ingredients", [])]

        data = _read(self.paths.potions_file, "potions", self.notices)
        if data:
            path = str(self.paths.potions_file)
            potions = [potion_from_dict(d, path) for d in data.get("potions", [])]

        return Catalog(ingredients, potions)

    # ── запись ────────────────────────────────────────────────────────────
    def _ingredients_payload(self, ingredients: list[Ingredient]) -> str:
        return dumps(
            {
                "schema_version": CURRENT_VERSIONS["ingredients"],
                "ingredients": [
                    ingredient_to_dict(i) for i in sorted(ingredients, key=lambda i: i.id)
                ],
            }
        )

    def _potions_payload(self, potions: list[Potion]) -> str:
        return dumps(
            {
                "schema_version": CURRENT_VERSIONS["potions"],
                "potions": [potion_to_dict(p) for p in sorted(potions, key=lambda p: p.id)],
            }
        )

    def save_ingredients(self, ingredients: list[Ingredient]) -> None:
        prepare_write(self.paths.ingredients_file, self._ingredients_payload(ingredients)).commit()

    def save_potions(self, potions: list[Potion]) -> None:
        prepare_write(self.paths.potions_file, self._potions_payload(potions)).commit()

    def save(self, catalog: Catalog) -> None:
        writes = [
            prepare_write(
                self.paths.ingredients_file, self._ingredients_payload(catalog.ingredients)
            ),
            prepare_write(self.paths.potions_file, self._potions_payload(catalog.potions)),
        ]
        commit_all(writes)


@dataclass(slots=True)
class JsonInventoryRepository:
    """`profiles/<id>/inventory.json` (03 §6.5)."""

    paths: Paths
    notices: list[Message] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.notices is None:
            self.notices = []

    def load(self) -> Inventory:
        self.notices.clear()
        data = _read(self.paths.inventory_file, "inventory", self.notices)
        if not data:
            return Inventory()
        return inventory_from_dict(data, str(self.paths.inventory_file))

    def payload(self, inventory: Inventory) -> str:
        return dumps(inventory_to_dict(inventory))

    def prepare(self, inventory: Inventory) -> PendingWrite:
        return prepare_write(self.paths.inventory_file, self.payload(inventory))

    def save(self, inventory: Inventory) -> None:
        self.prepare(inventory).commit()


@dataclass(slots=True)
class JsonJournalRepository:
    """`profiles/<id>/journal.json` (03 §6.6)."""

    paths: Paths
    notices: list[Message] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.notices is None:
            self.notices = []

    def load(self) -> list[JournalEntry]:
        self.notices.clear()
        data = _read(self.paths.journal_file, "journal", self.notices)
        if not data:
            return []
        path = str(self.paths.journal_file)
        entries = [entry_from_dict(d, path) for d in data.get("entries", [])]
        entries.sort(key=lambda e: e.ts)
        return entries

    def payload(self, entries: list[JournalEntry]) -> str:
        return dumps(
            {
                "schema_version": CURRENT_VERSIONS["journal"],
                "entries": [entry_to_dict(e) for e in sorted(entries, key=lambda e: e.ts)],
            }
        )

    def prepare(self, entries: list[JournalEntry]) -> PendingWrite:
        return prepare_write(self.paths.journal_file, self.payload(entries))

    def save(self, entries: list[JournalEntry]) -> None:
        self.prepare(entries).commit()


@dataclass(slots=True)
class JsonQueueRepository:
    """`profiles/<id>/queue.json` (03 §6.7)."""

    paths: Paths
    notices: list[Message] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.notices is None:
            self.notices = []

    def load(self) -> BrewQueue:
        self.notices.clear()
        data = _read(self.paths.queue_file, "queue", self.notices)
        if not data:
            return BrewQueue()
        return queue_from_dict(data, str(self.paths.queue_file))

    def save(self, queue: BrewQueue) -> None:
        prepare_write(self.paths.queue_file, dumps(queue_to_dict(queue))).commit()


def restore_from_backup(path: Path) -> None:
    """Откат на `.bak` по просьбе пользователя (NFR-8)."""
    backup = backup_path(path)
    if not backup.exists():
        raise StorageError(ErrorCode.NOT_FOUND, path=str(backup))
    prepare_write(path, backup.read_text(encoding="utf-8")).commit()
