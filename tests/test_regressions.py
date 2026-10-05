"""Найденное на полном разборе кода: каждая ошибка со своим тестом.

Все шесть падали молча — приложение работало, но показывало или делало не то.
"""

from __future__ import annotations

import pytest

from alchimist.core.elements import ElementVector as EV
from alchimist.core.matcher import StockItem, brewable
from alchimist.core.models import (
    ALL_BASES,
    BaseType,
    Ingredient,
    IngredientCategory,
    Kit,
    Potion,
    Rarity,
    Recipe,
)


def reagent(ident: str, name: str, rarity: Rarity, **elements: int) -> Ingredient:
    return Ingredient(
        id=ident,
        name=name,
        rarity=rarity,
        category=IngredientCategory.HERB,
        is_herb=True,
        elements=EV.from_dict(elements),
    )


# ── 1. Основы варианта не зависят от порядка наборов ─────────────────────────
def test_option_bases_merge_across_kits() -> None:
    """Травнику взрывная основа запрещена, алхимику — нет (П-6.3).

    Один и тот же набор реагентов разрешают оба, и раньше побеждал тот, кто
    нашёл вариант первым: с травником во главе списка взрывная основа у
    варианта молча пропадала.
    """
    herb = reagent("trava", "Трава", Rarity.COMMON, fire=1)
    potion = Potion(
        id="ogon",
        name="Огонь",
        rarity=Rarity.COMMON,
        recipe=Recipe(ALL_BASES, EV.from_dict({"fire": 2})),
    )
    stock = [StockItem(herb, 4)]

    forward = brewable([potion], stock, [Kit.ALCHEMIST, Kit.HERBALIST])[0].options[0]
    backward = brewable([potion], stock, [Kit.HERBALIST, Kit.ALCHEMIST])[0].options[0]

    assert forward.bases == ALL_BASES
    assert backward.bases == forward.bases
    # И оценка повторов берётся у того набора, которому видно больше запасов.
    assert backward.repeats == forward.repeats


def test_single_kit_keeps_its_own_limits() -> None:
    """Объединение основ не должно выдавать травнику лишнего."""
    herb = reagent("trava", "Трава", Rarity.COMMON, fire=1)
    potion = Potion(
        id="ogon",
        name="Огонь",
        rarity=Rarity.COMMON,
        recipe=Recipe(ALL_BASES, EV.from_dict({"fire": 2})),
    )
    option = brewable([potion], [StockItem(herb, 4)], [Kit.HERBALIST])[0].options[0]
    assert BaseType.EXPLOSIVE not in option.bases


# ── 2. Сводная строка «Могу сварить» действует по тому, что показала ─────────
@pytest.fixture
def divergent() -> tuple[Potion, list[StockItem]]:
    """Случай, где «самый простой» вариант и «самый дешёвый» — разные.

    Двойчатка одна даёт ровно две порции (Сл 12), а единственный способ сварить
    одну порцию — Глыба с довеском на три единицы (Сл 13).
    """
    potion = Potion(
        id="z",
        name="Зелье",
        rarity=Rarity.COMMON,
        recipe=Recipe(ALL_BASES, EV.from_dict({"fire": 1, "water": 1})),
    )
    stock = [
        StockItem(reagent("dbl", "Двойчатка", Rarity.EPIC, fire=2, water=2), 1),
        StockItem(reagent("big", "Глыба", Rarity.LEGENDARY, fire=1, water=1, earth=3), 1),
    ]
    return potion, stock


def test_easiest_and_best_really_can_differ(divergent) -> None:
    potion, stock = divergent
    row = brewable([potion], stock, [Kit.ALCHEMIST], max_excess=4, max_portions=3)[0]
    assert row.easiest.difficulty.total == 12
    assert row.best.difficulty.total == 13
    assert row.easiest is not row.best
