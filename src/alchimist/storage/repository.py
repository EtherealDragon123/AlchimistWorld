"""Интерфейсы репозиториев (03 §3).

Сервисы работают только через эти протоколы, поэтому хранилище можно заменить
(например на SQLite), не трогая слой выше.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from alchimist.core.models import (
    BrewQueue,
    Catalog,
    Ingredient,
    Inventory,
    JournalEntry,
    Potion,
)


@runtime_checkable
class CatalogRepository(Protocol):
    def load(self) -> Catalog: ...

    def save_ingredients(self, ingredients: list[Ingredient]) -> None: ...

    def save_potions(self, potions: list[Potion]) -> None: ...

    def save(self, catalog: Catalog) -> None: ...


@runtime_checkable
class InventoryRepository(Protocol):
    def load(self) -> Inventory: ...

    def save(self, inventory: Inventory) -> None: ...


@runtime_checkable
class JournalRepository(Protocol):
    def load(self) -> list[JournalEntry]: ...

    def save(self, entries: list[JournalEntry]) -> None: ...


@runtime_checkable
class QueueRepository(Protocol):
    def load(self) -> BrewQueue: ...

    def save(self, queue: BrewQueue) -> None: ...
