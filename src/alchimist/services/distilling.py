"""Дистилляция: разбор реагентов на эссенции (FR-13.x, П-9).

Сервис знает то, чего не знает `core.distill`: какие эссенции есть в справочнике,
сколько реагентов лежит в сумке и куда записать результат. Списание и запись в
журнал идут одной парой файлов, как и варка (03 §6.2), — на середине разбора
сумка не останется без реагентов и без эссенций разом.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from alchimist.core.distill import DistillPlan, essence_level, essence_name_ru, plan_distillation
from alchimist.core.elements import Element
from alchimist.core.errors import AlchimistError, ErrorCode, Message, Severity, error
from alchimist.core.models import (
    Ingredient,
    JournalEntry,
    JournalEntryType,
    Potion,
    ReagentStack,
)
from alchimist.services.catalog import CatalogService
from alchimist.services.events import EventBus, InventoryChanged, JournalChanged
from alchimist.services.inventory import InventoryService
from alchimist.services.journal import JournalService, new_id, now
from alchimist.storage.atomic import abort_all, commit_all

#: Зелье, в котором идёт разбор. Ищется по id из импорта, а если справочник
#: собирали руками — по названию.
EXTRACT_ID = "distilliruyushchiy-ekstrakt"
EXTRACT_NAME = "Дистиллирующий Экстракт"


@dataclass(frozen=True, slots=True)
class EssenceRow:
    """Строка результата: конкретная эссенция из справочника и сколько выйдет."""

    ingredient: Ingredient
    count: int
    level: int

    @property
    def name(self) -> str:
        return self.ingredient.name


@dataclass(frozen=True, slots=True)
class DistillPreview:
    """Что будет, если разобрать сейчас: без записи на диск."""

    plan: DistillPlan
    rows: tuple[EssenceRow, ...] = ()
    #: Экстракт, в котором идёт разбор, и сколько его в сумке.
    extract: Potion | None = None
    extract_qty: int = 0
    messages: tuple[Message, ...] = ()

    @property
    def errors(self) -> tuple[Message, ...]:
        return tuple(m for m in self.messages if m.severity is Severity.ERROR)

    @property
    def ok(self) -> bool:
        return bool(self.rows) and not self.errors

    @property
    def spends_extract(self) -> bool:
        """Уйдёт ли флакон. Без него разбора не бывает, так что при `ok` — всегда."""
        return self.extract is not None and self.extract_qty > 0

    @property
    def count(self) -> int:
        return sum(row.count for row in self.rows)


@dataclass(slots=True)
class DistillingService:
    catalog: CatalogService
    inventory: InventoryService
    journal: JournalService
    bus: EventBus

    # ── справочник ────────────────────────────────────────────────────────
    def essence_index(self) -> dict[tuple[Element, int], Ingredient]:
        """Эссенции по паре «стихия + уровень» (П-9.2)."""
        index: dict[tuple[Element, int], Ingredient] = {}
        for ingredient in self.catalog.ingredients(include_hidden=True):
            level = essence_level(ingredient)
            if level is None:
                continue
            element = next(iter(ingredient.elements.items()))[0]
            # Если названий на одну пару несколько, берётся первое по алфавиту:
            # разбор должен давать один и тот же результат от запуска к запуску.
            current = index.get((element, level))
            if current is None or ingredient.name.casefold() < current.name.casefold():
                index[(element, level)] = ingredient
        return index

    def essence(self, element: Element, level: int) -> Ingredient | None:
        return self.essence_index().get((element, level))

    def extract(self) -> Potion | None:
        """«Дистиллирующий Экстракт» из справочника, если он там есть."""
        potions = self.catalog.potion_map()
        found = potions.get(EXTRACT_ID)
        if found is not None:
            return found
        needle = EXTRACT_NAME.casefold()
        return next((p for p in potions.values() if p.name.casefold() == needle), None)

    # ── расчёт ────────────────────────────────────────────────────────────
    def preview(self, reagents: dict[str, int]) -> DistillPreview:
        """Что выйдет из экстракта и что этому мешает."""
        ingredients = self.catalog.ingredient_map()
        picked = [
            (ingredients[i], q) for i, q in sorted(reagents.items()) if q > 0 and i in ingredients
        ]
        plan = plan_distillation(picked)

        messages: list[Message] = list(plan.messages)
        have = self.inventory.reagent_quantities()
        for ingredient, qty in picked:
            if have.get(ingredient.id, 0) < qty:
                messages.append(
                    error(
                        ErrorCode.NOT_ENOUGH_REAGENTS,
                        id=ingredient.id,
                        name=ingredient.name,
                        have=have.get(ingredient.id, 0),
                        need=qty,
                    )
                )

        index = self.essence_index()
        rows: list[EssenceRow] = []
        for item in plan.yields:
            found = index.get((item.element, item.level))
            if found is None:
                messages.append(
                    error(ErrorCode.MISSING_ESSENCE, name=essence_name_ru(item.element, item.level))
                )
                continue
            rows.append(EssenceRow(found, item.count, item.level))

        potion = self.extract()
        qty = self.inventory.potion_qty(potion.id) if potion else 0
        if rows and qty <= 0:
            # Разбор идёт внутри флакона: нет флакона — нет и разбора (П-9.6).
            # Пустой экстракт сюда не попадает: там своя ошибка, про реагенты.
            messages.append(
                error(ErrorCode.DISTILL_NO_EXTRACT, name=potion.name if potion else EXTRACT_NAME)
            )

        return DistillPreview(
            plan=plan,
            rows=tuple(rows),
            extract=potion,
            extract_qty=qty,
            messages=tuple(messages),
        )

    # ── запись ────────────────────────────────────────────────────────────
    def distill(self, reagents: dict[str, int], note: str = "") -> JournalEntry:
        """Меняет реагенты на эссенции и пишет запись в журнал. Атомарно."""
        preview = self.preview(reagents)
        if not preview.ok:
            first = preview.errors[0] if preview.errors else error(ErrorCode.NO_REAGENTS)
            raise AlchimistError(first.code, **first.params)  # type: ignore[arg-type]

        picked = {i: q for i, q in reagents.items() if q > 0}
        inventory = self.inventory.consume_preview(picked)
        for row in preview.rows:
            was = inventory.reagent_qty(row.ingredient.id)
            inventory = self.inventory.with_reagent(
                inventory, row.ingredient.id, was + row.count, None
            )

        # Без флакона `preview.ok` не бывает (П-9.6), так что сюда мы попадаем
        # только с ним. Условие оставлено ради записей, созданных до этого правила:
        # их отмена читает `potion_id` и `qty` и одинаково работает с нулём.
        potion_ids: tuple[str, ...] = ()
        spent = preview.spends_extract
        if spent and preview.extract is not None:
            inventory = self.inventory.with_potion(
                inventory, preview.extract.id, preview.extract_qty - 1, None
            )
            potion_ids = (preview.extract.id,)

        entry = JournalEntry(
            id=new_id(),
            ts=now(),
            type=JournalEntryType.DISTILL,
            reagents=tuple(ReagentStack(i, q) for i, q in sorted(picked.items())),
            elements=preview.plan.elements,
            produced=tuple(
                ReagentStack(row.ingredient.id, row.count)
                for row in sorted(preview.rows, key=lambda r: r.ingredient.id)
            ),
            potion_id=preview.extract.id if spent and preview.extract else None,
            qty=1 if spent else 0,
            note=note,
        )

        self._commit(inventory, entry, replace_existing=False)
        changed = (*picked, *(row.ingredient.id for row in preview.rows))
        self.bus.publish(InventoryChanged(tuple(changed), potion_ids))
        self.bus.publish(JournalChanged((entry.id,)))
        return entry

    def undo(self, entry_id: str) -> JournalEntry:
        """Возвращает реагенты, забирает эссенции, помечает запись отменённой."""
        entry = self.journal.entry(entry_id)
        if entry.type is not JournalEntryType.DISTILL or entry.undone:
            raise AlchimistError(ErrorCode.NOT_FOUND, id=entry_id)

        ingredients = self.catalog.ingredient_map()
        inventory = self.inventory.inventory
        for stack in entry.produced:
            was = inventory.reagent_qty(stack.ingredient_id)
            if was < stack.qty:
                found = ingredients.get(stack.ingredient_id)
                raise AlchimistError(
                    ErrorCode.NOT_ENOUGH_REAGENTS,
                    id=stack.ingredient_id,
                    name=found.name if found else stack.ingredient_id,
                    have=was,
                    need=stack.qty,
                )
            inventory = self.inventory.with_reagent(
                inventory, stack.ingredient_id, was - stack.qty, None
            )
        for stack in entry.reagents:
            was = inventory.reagent_qty(stack.ingredient_id)
            inventory = self.inventory.with_reagent(
                inventory, stack.ingredient_id, was + stack.qty, None
            )

        potion_ids: tuple[str, ...] = ()
        if entry.potion_id and entry.qty:
            was = inventory.potion_qty(entry.potion_id)
            inventory = self.inventory.with_potion(
                inventory, entry.potion_id, was + entry.qty, None
            )
            potion_ids = (entry.potion_id,)

        undone = replace(entry, undone=True)
        self._commit(inventory, undone, replace_existing=True)
        changed = (
            *(s.ingredient_id for s in entry.reagents),
            *(s.ingredient_id for s in entry.produced),
        )
        self.bus.publish(InventoryChanged(changed, potion_ids))
        self.bus.publish(JournalChanged((entry.id,)))
        return undone

    def _commit(self, inventory, entry: JournalEntry, *, replace_existing: bool) -> None:
        """Инвентарь и журнал кладутся на диск вместе (03 §6.2)."""
        existing = self.journal.entries(newest_first=False)
        entries = (
            [entry if e.id == entry.id else e for e in existing]
            if replace_existing
            else [*existing, entry]
        )
        writes = [
            self.inventory.prepare_write(inventory),
            self.journal.prepare_write(entries),
        ]
        try:
            commit_all(writes)
        except OSError:
            abort_all(writes)
            raise
        self.inventory.adopt(inventory)
        self.journal.adopt(entries)
