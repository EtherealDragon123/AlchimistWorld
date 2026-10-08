"""Правила дистилляции (П-9)."""

from __future__ import annotations

import pytest

from alchimist.core.distill import (
    MAX_REAGENTS,
    DistillPlan,
    essence_level,
    essence_name_ru,
    plan_distillation,
    split_units,
)
from alchimist.core.elements import Element
from alchimist.core.elements import ElementVector as EV
from alchimist.core.errors import ErrorCode
from alchimist.core.models import Ingredient, IngredientCategory, Rarity

LEVEL_RARITY = {
    1: Rarity.COMMON,
    2: Rarity.UNCOMMON,
    3: Rarity.RARE,
    4: Rarity.EPIC,
    5: Rarity.LEGENDARY,
}


def essence(element: str, level: int) -> Ingredient:
    """Эссенция с лестницы: единиц ровно столько, какова редкость (П-3.2)."""
    return Ingredient(
        id=f"{element}-{level}",
        name=essence_name_ru(Element(element), level),
        rarity=LEVEL_RARITY[level],
        category=IngredientCategory.ESSENCE,
        elements=EV.from_dict({element: level}),
    )


def reagent(ident: str, **elements: int) -> Ingredient:
    total = sum(elements.values())
    return Ingredient(
        id=ident,
        name=ident,
        rarity=LEVEL_RARITY[total],
        category=IngredientCategory.PLANT,
        elements=EV.from_dict(elements),
    )


def yields_of(plan: DistillPlan) -> list[tuple[str, int, int]]:
    return [(y.element.value, y.level, y.count) for y in plan.yields]


# ── П-9.2: как дробятся единицы ──────────────────────────────────────────────
@pytest.mark.parametrize(
    ("units", "expected"),
    [
        (0, []),
        (1, [1]),
        (3, [3]),
        (5, [5]),
        (6, [5, 1]),
        (7, [5, 2]),
        (10, [5, 5]),
        (11, [5, 5, 1]),
    ],
)
def test_split_units_takes_the_largest_first(units: int, expected: list[int]) -> None:
    assert split_units(units) == expected


def test_dm_example_seven_earth() -> None:
    """Пример мастера: 7 единиц земли → сияющая (5) и тусклая (2)."""
    plan = plan_distillation([(reagent("глина", earth=3), 1), (reagent("камень", earth=4), 1)])
    assert plan.ok
    assert plan.elements == EV.from_dict({"earth": 7})
    assert yields_of(plan) == [("earth", 5, 1), ("earth", 2, 1)]


def test_each_element_is_distilled_on_its_own() -> None:
    """П-9.3: стихии не смешиваются, каждая считается отдельно."""
    plan = plan_distillation([(reagent("уголь", fire=4), 1), (reagent("ил", earth=3, water=2), 1)])
    assert yields_of(plan) == [("fire", 4, 1), ("water", 2, 1), ("earth", 3, 1)]


def test_five_units_stay_one_essence() -> None:
    plan = plan_distillation([(reagent("слиток", earth=5), 1)])
    assert yields_of(plan) == [("earth", 5, 1)]


def test_same_essences_are_grouped() -> None:
    plan = plan_distillation([(reagent("глыба", earth=5), 2)])
    assert yields_of(plan) == [("earth", 5, 2)]


# ── П-9.1: сколько влезает в экстракт ────────────────────────────────────────
def test_more_than_five_reagents_is_refused() -> None:
    plan = plan_distillation([(reagent("трава", fire=1), MAX_REAGENTS + 1)])
    assert not plan.ok
    assert [m.code for m in plan.errors] == [ErrorCode.TOO_MANY_REAGENTS]
    assert plan.reagents == MAX_REAGENTS + 1


def test_exactly_five_reagents_is_fine() -> None:
    plan = plan_distillation([(reagent("трава", fire=1), MAX_REAGENTS)])
    assert plan.ok
    assert yields_of(plan) == [("fire", 5, 1)]


def test_empty_extract() -> None:
    assert [m.code for m in plan_distillation([]).errors] == [ErrorCode.NO_REAGENTS]


# ── П-9.4: эссенции вместе с реагентами считаются как все ────────────────────
def test_essence_with_a_reagent_counts_normally() -> None:
    """Тусклая эссенция огня (2) плюс реагент на 1 огня = сверкающая (3)."""
    plan = plan_distillation([(essence("fire", 2), 1), (reagent("щёлкорех", fire=1), 1)])
    assert plan.ok
    assert not plan.broken_down
    assert yields_of(plan) == [("fire", 3, 1)]


def test_two_essences_of_one_element_merge() -> None:
    plan = plan_distillation([(essence("fire", 2), 2)])
    assert plan.ok
    assert not plan.broken_down
    assert yields_of(plan) == [("fire", 4, 1)]


def test_essences_of_different_elements_change_nothing() -> None:
    """Слить разные стихии нельзя: на выходе будет то же самое."""
    plan = plan_distillation([(essence("fire", 2), 1), (essence("water", 2), 1)])
    assert not plan.ok
    assert [m.code for m in plan.errors] == [ErrorCode.DISTILL_NO_CHANGE]


# ── П-9.5: одинокая эссенция рассыпается ─────────────────────────────────────
@pytest.mark.parametrize("level", [2, 3, 4, 5])
def test_lone_essence_breaks_into_phosphorescent(level: int) -> None:
    plan = plan_distillation([(essence("earth", level), 1)])
    assert plan.ok
    assert plan.broken_down
    assert yields_of(plan) == [("earth", 1, level)]


def test_lone_phosphorescent_essence_has_nowhere_to_go() -> None:
    plan = plan_distillation([(essence("earth", 1), 1)])
    assert not plan.ok
    assert [m.code for m in plan.errors] == [ErrorCode.DISTILL_NO_CHANGE]


def test_breakdown_needs_the_essence_to_be_alone() -> None:
    """Две тусклые — это уже обычная схема: они сольются, а не рассыплются."""
    plan = plan_distillation([(essence("earth", 2), 2)])
    assert not plan.broken_down
    assert yields_of(plan) == [("earth", 4, 1)]


# ── мелочи ───────────────────────────────────────────────────────────────────
def test_essence_level_reads_the_ladder() -> None:
    assert essence_level(essence("fire", 3)) == 3
    assert essence_level(reagent("щёлкорех", fire=1)) is None
    # Эссенция двух стихий лестнице не принадлежит.
    mixed = Ingredient(
        id="mixed",
        name="смесь",
        category=IngredientCategory.ESSENCE,
        elements=EV.from_dict({"fire": 1, "water": 1}),
    )
    assert essence_level(mixed) is None


def test_essence_name() -> None:
    assert essence_name_ru(Element.EARTH, 5) == "Сияющая эссенция земли"
