"""Дистилляция целиком: справочник, сумка, журнал (FR-13.x, П-9)."""

from __future__ import annotations

import pytest

from alchimist.core.distill import LEVEL_NAMES_RU, essence_name_ru
from alchimist.core.elements import ELEMENT_ORDER, Element
from alchimist.core.elements import ElementVector as EV
from alchimist.core.errors import AlchimistError, ErrorCode
from alchimist.core.models import (
    ALL_BASES,
    Catalog,
    Ingredient,
    IngredientCategory,
    JournalEntryType,
    Potion,
    Rarity,
    Recipe,
)
from alchimist.services.app import AppService
from alchimist.services.distilling import EXTRACT_ID

EXTRACT = Potion(
    id=EXTRACT_ID,
    name="Дистиллирующий Экстракт",
    rarity=Rarity.UNCOMMON,
    recipe=Recipe(ALL_BASES, EV.from_dict({"fire": 1, "water": 1, "dark": 1})),
)


def essence_id(element: Element, level: int) -> str:
    return f"essence-{element.value}-{level}"


def ladder() -> list[Ingredient]:
    """Все 35 эссенций: семь стихий на пять ступеней."""
    return [
        Ingredient(
            id=essence_id(element, level),
            name=essence_name_ru(element, level),
            rarity=Rarity(level),
            category=IngredientCategory.ESSENCE,
            elements=EV.from_dict({element.value: level}),
        )
        for element in ELEMENT_ORDER
        for level in LEVEL_NAMES_RU
    ]


@pytest.fixture
def lab(app: AppService, catalog: Catalog) -> AppService:
    """Справочник фикстуры плюс полная лестница эссенций и сам экстракт."""
    keep = [i for i in catalog.ingredients if i.category is not IngredientCategory.ESSENCE]
    app.catalog.replace_all(Catalog([*keep, *ladder()], [*catalog.potions, EXTRACT]))
    app.inventory.set_potion(EXTRACT_ID, 3)
    return app


def produced(app: AppService, entry) -> dict[str, int]:
    return {s.ingredient_id: s.qty for s in entry.produced}


# ── подбор эссенций по справочнику ───────────────────────────────────────────
def test_preview_resolves_real_essences(lab: AppService) -> None:
    """7 единиц земли: сияющая и тусклая — именно те, что лежат в справочнике."""
    lab.inventory.set_reagent("sok-stalnogo-dereva", 3)  # Земля×2
    lab.inventory.set_reagent("tkanevyy-list", 1)  # Земля×1
    preview = lab.distilling.preview({"sok-stalnogo-dereva": 3, "tkanevyy-list": 1})

    assert preview.ok
    assert preview.plan.elements == EV.from_dict({"earth": 7})
    assert [(r.ingredient.name, r.count) for r in preview.rows] == [
        ("Сияющая эссенция земли", 1),
        ("Тусклая эссенция земли", 1),
    ]
    assert preview.spends_extract


def test_preview_flags_missing_reagents(lab: AppService) -> None:
    lab.inventory.set_reagent("tkanevyy-list", 1)
    preview = lab.distilling.preview({"tkanevyy-list": 3})
    assert not preview.ok
    assert [m.code for m in preview.errors] == [ErrorCode.NOT_ENOUGH_REAGENTS]


def test_preview_refuses_without_an_extract(lab: AppService) -> None:
    """П-9.6: разбирать не в чем — без флакона дистилляции нет."""
    lab.inventory.set_potion(EXTRACT_ID, 0)
    lab.inventory.set_reagent("sok-stalnogo-dereva", 1)
    preview = lab.distilling.preview({"sok-stalnogo-dereva": 1})
    assert not preview.ok
    assert not preview.spends_extract
    assert [m.code for m in preview.errors] == [ErrorCode.DISTILL_NO_EXTRACT]


def test_empty_extract_complains_about_reagents_not_the_flask(lab: AppService) -> None:
    """Пустой набор — это про реагенты; флакон тут ни при чём."""
    lab.inventory.set_potion(EXTRACT_ID, 0)
    preview = lab.distilling.preview({})
    assert [m.code for m in preview.errors] == [ErrorCode.NO_REAGENTS]


def test_missing_essence_in_catalog_is_reported(app: AppService) -> None:
    """Справочник без эссенций: разбирать некуда, и это видно."""
    app.inventory.set_reagent("tkanevyy-list", 1)
    preview = app.distilling.preview({"tkanevyy-list": 1})
    assert not preview.ok
    assert [m.code for m in preview.errors] == [ErrorCode.MISSING_ESSENCE]


# ── сам разбор ───────────────────────────────────────────────────────────────
def test_distill_swaps_reagents_for_essences(lab: AppService) -> None:
    lab.inventory.set_reagent("sok-stalnogo-dereva", 3)
    lab.inventory.set_reagent("tkanevyy-list", 1)
    entry = lab.distilling.distill({"sok-stalnogo-dereva": 3, "tkanevyy-list": 1})

    assert lab.inventory.reagent_qty("sok-stalnogo-dereva") == 0
    assert lab.inventory.reagent_qty("tkanevyy-list") == 0
    assert lab.inventory.reagent_qty(essence_id(Element.EARTH, 5)) == 1
    assert lab.inventory.reagent_qty(essence_id(Element.EARTH, 2)) == 1
    # Флакон экстракта уходит вместе с реагентами (П-9.6).
    assert lab.inventory.potion_qty(EXTRACT_ID) == 2

    assert entry.type is JournalEntryType.DISTILL
    assert entry.elements == EV.from_dict({"earth": 7})
    assert produced(lab, entry) == {
        essence_id(Element.EARTH, 5): 1,
        essence_id(Element.EARTH, 2): 1,
    }
    assert entry.potion_id == EXTRACT_ID and entry.qty == 1


def test_distill_adds_to_what_is_already_there(lab: AppService) -> None:
    lab.inventory.set_reagent("sok-stalnogo-dereva", 1)
    lab.inventory.set_reagent(essence_id(Element.EARTH, 2), 4)
    lab.distilling.distill({"sok-stalnogo-dereva": 1})
    assert lab.inventory.reagent_qty(essence_id(Element.EARTH, 2)) == 5


def test_lone_essence_breaks_down(lab: AppService) -> None:
    """П-9.5: сияющая эссенция огня в одиночку рассыпается на пять фосфорицирующих."""
    lab.inventory.set_reagent(essence_id(Element.FIRE, 5), 1)
    lab.distilling.distill({essence_id(Element.FIRE, 5): 1})
    assert lab.inventory.reagent_qty(essence_id(Element.FIRE, 5)) == 0
    assert lab.inventory.reagent_qty(essence_id(Element.FIRE, 1)) == 5


def test_essences_merge_with_a_reagent(lab: AppService) -> None:
    """П-9.4: тусклая эссенция огня (2) плюс Щёлкорех (1) = сверкающая (3)."""
    lab.inventory.set_reagent(essence_id(Element.FIRE, 2), 1)
    lab.inventory.set_reagent("shcholkorekh", 1)
    lab.distilling.distill({essence_id(Element.FIRE, 2): 1, "shcholkorekh": 1})
    assert lab.inventory.reagent_qty(essence_id(Element.FIRE, 3)) == 1
    assert lab.inventory.reagent_qty(essence_id(Element.FIRE, 2)) == 0


def test_distill_without_an_extract_is_refused(lab: AppService) -> None:
    lab.inventory.set_potion(EXTRACT_ID, 0)
    lab.inventory.set_reagent("sok-stalnogo-dereva", 1)
    with pytest.raises(AlchimistError) as exc:
        lab.distilling.distill({"sok-stalnogo-dereva": 1})
    assert exc.value.code is ErrorCode.DISTILL_NO_EXTRACT
    # Сумка не тронута: реагент на месте, эссенций не появилось.
    assert lab.inventory.reagent_qty("sok-stalnogo-dereva") == 1
    assert lab.inventory.reagent_qty(essence_id(Element.EARTH, 2)) == 0


def test_undo_still_works_for_entries_made_without_a_flask(lab: AppService) -> None:
    """Записи, сделанные до П-9.6, отменяются как раньше: флакона там нет."""
    from dataclasses import replace

    lab.inventory.set_reagent("sok-stalnogo-dereva", 1)
    entry = lab.distilling.distill({"sok-stalnogo-dereva": 1})
    lab.journal.replace(replace(entry, potion_id=None, qty=0))

    lab.distilling.undo(entry.id)
    assert lab.inventory.reagent_qty("sok-stalnogo-dereva") == 1
    assert lab.inventory.reagent_qty(essence_id(Element.EARTH, 2)) == 0
    # Флакон не возвращается: в записи его не было.
    assert lab.inventory.potion_qty(EXTRACT_ID) == 2


def test_too_many_reagents_is_refused(lab: AppService) -> None:
    lab.inventory.set_reagent("tkanevyy-list", 6)
    with pytest.raises(AlchimistError) as exc:
        lab.distilling.distill({"tkanevyy-list": 6})
    assert exc.value.code is ErrorCode.TOO_MANY_REAGENTS
    assert lab.inventory.reagent_qty("tkanevyy-list") == 6


def test_pointless_distillation_is_refused(lab: AppService) -> None:
    lab.inventory.set_reagent(essence_id(Element.FIRE, 1), 1)
    with pytest.raises(AlchimistError) as exc:
        lab.distilling.distill({essence_id(Element.FIRE, 1): 1})
    assert exc.value.code is ErrorCode.DISTILL_NO_CHANGE


# ── отмена ───────────────────────────────────────────────────────────────────
def test_undo_puts_everything_back(lab: AppService) -> None:
    lab.inventory.set_reagent("sok-stalnogo-dereva", 3)
    lab.inventory.set_reagent("tkanevyy-list", 1)
    entry = lab.distilling.distill({"sok-stalnogo-dereva": 3, "tkanevyy-list": 1})
    undone = lab.distilling.undo(entry.id)

    assert undone.undone
    assert lab.inventory.reagent_qty("sok-stalnogo-dereva") == 3
    assert lab.inventory.reagent_qty("tkanevyy-list") == 1
    assert lab.inventory.reagent_qty(essence_id(Element.EARTH, 5)) == 0
    assert lab.inventory.potion_qty(EXTRACT_ID) == 3


def test_undo_needs_the_essences_to_still_be_there(lab: AppService) -> None:
    lab.inventory.set_reagent("sok-stalnogo-dereva", 1)
    entry = lab.distilling.distill({"sok-stalnogo-dereva": 1})
    lab.inventory.set_reagent(essence_id(Element.EARTH, 2), 0)
    with pytest.raises(AlchimistError) as exc:
        lab.distilling.undo(entry.id)
    assert exc.value.code is ErrorCode.NOT_ENOUGH_REAGENTS


def test_undo_twice_is_refused(lab: AppService) -> None:
    lab.inventory.set_reagent("sok-stalnogo-dereva", 1)
    entry = lab.distilling.distill({"sok-stalnogo-dereva": 1})
    lab.distilling.undo(entry.id)
    with pytest.raises(AlchimistError):
        lab.distilling.undo(entry.id)


def test_entry_survives_a_reload(lab: AppService) -> None:
    """Запись о разборе должна читаться с диска: у журнала новая схема."""
    lab.inventory.set_reagent("sok-stalnogo-dereva", 1)
    entry = lab.distilling.distill({"sok-stalnogo-dereva": 1})
    lab.journal.reload()
    again = lab.journal.entry(entry.id)
    assert again.type is JournalEntryType.DISTILL
    assert again.elements == EV.from_dict({"earth": 2})
    assert produced(lab, again) == {essence_id(Element.EARTH, 2): 1}
    assert again.potion_id == EXTRACT_ID
