"""Инвентарь реагентов и зелий (FR-3.x, FR-4.x)."""

from __future__ import annotations

from dataclasses import dataclass, field

from alchimist.core.elements import ElementVector
from alchimist.core.errors import AlchimistError, ErrorCode, Message
from alchimist.core.models import Ingredient, Inventory, Potion, PotionStack, ReagentStack
from alchimist.services.events import EventBus, InventoryChanged
from alchimist.storage.repository import InventoryRepository


@dataclass(frozen=True, slots=True)
class ReagentRow:
    """Строка экрана «Реагенты» (FR-3.1)."""

    ingredient: Ingredient
    qty: int
    note: str = ""


@dataclass(frozen=True, slots=True)
class PotionRow:
    """Строка экрана «Мои зелья» (FR-4.1)."""

    potion: Potion
    qty: int
    note: str = ""


@dataclass(slots=True)
class InventoryService:
    repo: InventoryRepository
    bus: EventBus
    _inventory: Inventory = field(default_factory=Inventory)
    _notices: list[Message] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        self._inventory = self.repo.load()
        self._notices = list(getattr(self.repo, "notices", []) or [])

    @property
    def notices(self) -> list[Message]:
        return list(self._notices)

    @property
    def inventory(self) -> Inventory:
        return self._inventory

    # ── чтение ────────────────────────────────────────────────────────────
    def reagent_quantities(self) -> dict[str, int]:
        return self._inventory.reagent_map()

    def reagent_qty(self, ingredient_id: str) -> int:
        return self._inventory.reagent_qty(ingredient_id)

    def potion_qty(self, potion_id: str) -> int:
        return self._inventory.potion_qty(potion_id)

    def reagent_rows(self, ingredients: dict[str, Ingredient]) -> list[ReagentRow]:
        rows = [
            ReagentRow(ingredients[s.ingredient_id], s.qty, s.note)
            for s in self._inventory.reagents
            if s.qty > 0 and s.ingredient_id in ingredients
        ]
        rows.sort(key=lambda r: r.ingredient.name.casefold())
        return rows

    def potion_rows(self, potions: dict[str, Potion]) -> list[PotionRow]:
        rows = [
            PotionRow(potions[s.potion_id], s.qty, s.note)
            for s in self._inventory.potions
            if s.qty > 0 and s.potion_id in potions
        ]
        rows.sort(key=lambda r: (r.potion.rarity, r.potion.name.casefold()))
        return rows

    def element_summary(self, ingredients: dict[str, Ingredient]) -> ElementVector:
        """Сколько всего единиц каждого элемента лежит в сумке (FR-3.5)."""
        total = ElementVector()
        for stack in self._inventory.reagents:
            ingredient = ingredients.get(stack.ingredient_id)
            if ingredient and stack.qty > 0:
                total = total + ingredient.elements * stack.qty
        return total

    def unknown_ids(
        self, ingredients: dict[str, Ingredient], potions: dict[str, Potion]
    ) -> list[str]:
        """Что лежит в инвентаре, но пропало из справочника (NFR-8)."""
        missing = [
            s.ingredient_id for s in self._inventory.reagents if s.ingredient_id not in ingredients
        ]
        missing += [s.potion_id for s in self._inventory.potions if s.potion_id not in potions]
        return missing

    def is_ingredient_used(self, ingredient_id: str) -> bool:
        return self._inventory.reagent_qty(ingredient_id) > 0

    def is_potion_used(self, potion_id: str) -> bool:
        return self._inventory.potion_qty(potion_id) > 0

    # ── запись ────────────────────────────────────────────────────────────
    def _apply(self, inventory: Inventory, ingredient_ids=(), potion_ids=()) -> None:
        self._inventory = inventory
        self.repo.save(inventory)
        self.bus.publish(InventoryChanged(tuple(ingredient_ids), tuple(potion_ids)))

    @staticmethod
    def with_reagent(
        inventory: Inventory, ingredient_id: str, qty: int, note: str | None
    ) -> Inventory:
        """qty ≤ 0 — строка исчезает (FR-3.2)."""
        stacks = [s for s in inventory.reagents if s.ingredient_id != ingredient_id]
        old = next((s for s in inventory.reagents if s.ingredient_id == ingredient_id), None)
        if qty > 0:
            stacks.append(
                ReagentStack(
                    ingredient_id, qty, note if note is not None else (old.note if old else "")
                )
            )
        stacks.sort(key=lambda s: s.ingredient_id)
        return Inventory(tuple(stacks), inventory.potions)

    @staticmethod
    def with_potion(inventory: Inventory, potion_id: str, qty: int, note: str | None) -> Inventory:
        stacks = [s for s in inventory.potions if s.potion_id != potion_id]
        old = next((s for s in inventory.potions if s.potion_id == potion_id), None)
        if qty > 0:
            stacks.append(
                PotionStack(potion_id, qty, note if note is not None else (old.note if old else ""))
            )
        stacks.sort(key=lambda s: s.potion_id)
        return Inventory(inventory.reagents, tuple(stacks))

    def set_reagent(self, ingredient_id: str, qty: int, note: str | None = None) -> None:
        self._apply(
            self.with_reagent(self._inventory, ingredient_id, max(0, qty), note),
            ingredient_ids=(ingredient_id,),
        )

    def add_reagent(self, ingredient_id: str, delta: int = 1) -> int:
        qty = max(0, self._inventory.reagent_qty(ingredient_id) + delta)
        self.set_reagent(ingredient_id, qty)
        return qty

    def set_potion(self, potion_id: str, qty: int, note: str | None = None) -> None:
        self._apply(
            self.with_potion(self._inventory, potion_id, max(0, qty), note),
            potion_ids=(potion_id,),
        )

    def add_potion(self, potion_id: str, delta: int = 1) -> int:
        qty = max(0, self._inventory.potion_qty(potion_id) + delta)
        self.set_potion(potion_id, qty)
        return qty

    def set_reagent_note(self, ingredient_id: str, note: str) -> None:
        self.set_reagent(ingredient_id, self._inventory.reagent_qty(ingredient_id), note)

    def set_potion_note(self, potion_id: str, note: str) -> None:
        """Свободная заметка к позиции инвентаря (FR-4.5)."""
        self.set_potion(potion_id, self._inventory.potion_qty(potion_id), note)

    def take_potion(self, potion_id: str, qty: int = 1) -> None:
        """Использование зелья (FR-4.2). Запись в журнал делает BrewingService."""
        have = self._inventory.potion_qty(potion_id)
        if have < qty:
            raise AlchimistError(ErrorCode.NOT_ENOUGH_POTIONS, id=potion_id, have=have, need=qty)
        self.set_potion(potion_id, have - qty)

    # ── подготовка списания для варки (FR-7.2) ────────────────────────────
    def consume_preview(self, reagents: dict[str, int]) -> Inventory:
        """Инвентарь после списания. Не хватает — ошибка, инвентарь не меняется."""
        inventory = self._inventory
        for ingredient_id, qty in reagents.items():
            have = inventory.reagent_qty(ingredient_id)
            if have < qty:
                raise AlchimistError(
                    ErrorCode.NOT_ENOUGH_REAGENTS, id=ingredient_id, have=have, need=qty
                )
            inventory = self.with_reagent(inventory, ingredient_id, have - qty, None)
        return inventory

    # ── совместная запись с журналом (03 §6.2) ────────────────────────────
    def prepare_write(self, inventory: Inventory):
        """Готовит `.tmp` без подмены: варка меняет два файла разом."""
        return self.repo.prepare(inventory)  # type: ignore[attr-defined]

    def adopt(self, inventory: Inventory) -> None:
        """Принимает уже записанный на диск инвентарь, не трогая файлы."""
        self._inventory = inventory
