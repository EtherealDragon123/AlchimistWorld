"""Сложность приготовления и правила о порциях и лишних эссенциях (П-8)."""

from __future__ import annotations

import pytest

from alchimist.core.elements import ElementVector as EV
from alchimist.core.matcher import (
    brewable,
    find_combinations,
    portions_and_excess,
    read_as_portions,
    stock_from,
)
from alchimist.core.models import BaseType, Ingredient, Kit, Potion, Rarity
from alchimist.core.rules import brew_difficulty


# ── П-8.3: базовая сложность и редкость ──────────────────────────────────────
def test_base_difficulty_by_rarity() -> None:
    assert [brew_difficulty(r).total for r in Rarity] == [10, 12, 14, 16, 18]


def test_portions_add_two_each() -> None:
    """П-8.2: каждая порция сверх первой — +2."""
    assert brew_difficulty(Rarity.COMMON, portions=1).total == 10
    assert brew_difficulty(Rarity.COMMON, portions=2).total == 12
    assert brew_difficulty(Rarity.COMMON, portions=3).total == 14


def test_excess_adds_one_each() -> None:
    """П-8.1: каждая лишняя эссенция — +1."""
    assert brew_difficulty(Rarity.COMMON, excess_units=1).total == 11
    assert brew_difficulty(Rarity.COMMON, excess_units=4).total == 14


def test_dm_worked_example() -> None:
    """Пример мастера: 2 порции эпического зелья с одной лишней эссенцией."""
    difficulty = brew_difficulty(Rarity.EPIC, portions=2, excess_units=1)
    assert difficulty.format_ru() == "10 + 6 + 2 + 1 = 19"
    assert difficulty.total == 19


def test_parts_are_separate() -> None:
    d = brew_difficulty(Rarity.RARE, portions=3, excess_units=2)
    assert [value for _name, value in d.parts()] == [10, 4, 4, 2]
    assert d.total == 20


# ── П-8.1, П-8.2: порции и остаток ───────────────────────────────────────────
def test_portions_and_excess() -> None:
    recipe = EV.from_dict({"fire": 1, "water": 1, "dark": 1})
    assert portions_and_excess(EV.from_dict({"fire": 1, "water": 1, "dark": 1}), recipe) == (
        1,
        EV(),
    )
    assert portions_and_excess(EV.from_dict({"fire": 2, "water": 2, "dark": 2}), recipe) == (
        2,
        EV(),
    )
    portions, excess = portions_and_excess(
        EV.from_dict({"fire": 2, "water": 1, "dark": 1, "light": 3}), recipe
    )
    assert portions == 1
    assert excess.to_dict() == {"fire": 1, "light": 3}


def test_not_enough_gives_no_portions() -> None:
    recipe = EV.from_dict({"fire": 2})
    assert portions_and_excess(EV.from_dict({"fire": 1, "water": 9}), recipe)[0] == 0


# ── подбор с излишком ────────────────────────────────────────────────────────
def test_exact_search_unchanged_by_default(ingredients: dict[str, Ingredient]) -> None:
    """Без разрешения на лишнее подбор работает как прежде (П-5.4)."""
    stock = stock_from(ingredients, {"krov-drakocherepakhi": 3})
    assert find_combinations(EV.from_dict({"fire": 2}), stock) == []


def test_excess_opens_previously_impossible(ingredients: dict[str, Ingredient]) -> None:
    """П-8.1: Кровь дракочерепахи плюс Щёлкорех дают Огонь×2 с лишней Водой×2."""
    stock = stock_from(ingredients, {"krov-drakocherepakhi": 1, "shcholkorekh": 1})
    combos = find_combinations(EV.from_dict({"fire": 2}), stock, max_excess=2)
    assert len(combos) == 1
    assert combos[0].excess.to_dict() == {"water": 2}
    assert combos[0].excess_units == 2
    assert not combos[0].is_exact


def test_excess_budget_is_respected(ingredients: dict[str, Ingredient]) -> None:
    stock = stock_from(ingredients, {"krov-drakocherepakhi": 1, "shcholkorekh": 1})
    assert find_combinations(EV.from_dict({"fire": 2}), stock, max_excess=1) == []


def test_dominated_variants_are_dropped(ingredients: dict[str, Ingredient]) -> None:
    """Набор, куда доложили лишнего поверх уже готового, — не вариант, а мусор."""
    stock = stock_from(ingredients, {"krov-drakocherepakhi": 1, "shcholkorekh": 5})
    combos = find_combinations(EV.from_dict({"fire": 2}), stock, max_excess=4)
    for combo in combos:
        assert combo.excess_units <= 2, combo.as_map()


def test_exact_variant_comes_first(ingredients: dict[str, Ingredient]) -> None:
    stock = stock_from(ingredients, {"krov-drakocherepakhi": 1, "shcholkorekh": 2})
    combos = find_combinations(EV.from_dict({"fire": 2}), stock, max_excess=3)
    assert combos[0].is_exact
    assert [(p.ingredient.name, p.count) for p in combos[0].picks] == [("Щёлкорех", 2)]


# ── П-8.2: несколько порций ──────────────────────────────────────────────────
def test_dm_two_portions_example(
    ingredients: dict[str, Ingredient], potions: dict[str, Potion]
) -> None:
    """Пример мастера: Кровь дракочерепахи и Семя ночного пламени → 2 порции Экстракта."""
    from alchimist.core.models import Recipe

    extract = Potion(
        id="ekstrakt",
        name="Дистиллирующий Экстракт",
        rarity=Rarity.UNCOMMON,
        recipe=Recipe(
            frozenset({BaseType.LIQUID}), EV.from_dict({"fire": 1, "water": 1, "dark": 1})
        ),
    )
    stock = stock_from(ingredients, {"krov-drakocherepakhi": 1, "semya-nochnogo-plameni": 1})
    rows = brewable([extract], stock, [Kit.ALCHEMIST], max_excess=2, max_portions=3)

    assert len(rows) == 1
    option = rows[0].best
    assert option.portions == 2
    assert option.combination.is_exact
    assert option.difficulty.total == 14
    assert option.difficulty.format_ru() == "10 + 2 + 2 + 0 = 14"
    assert sorted(option.combination.as_map()) == [
        "krov-drakocherepakhi",
        "semya-nochnogo-plameni",
    ]


def test_read_as_portions_prefers_more_portions() -> None:
    """Одна горсть читается как больше порций, а не как куча лишнего."""
    from alchimist.core.matcher import Combination, Pick
    from alchimist.core.models import IngredientCategory

    double = Ingredient(
        "x",
        "Двойная трава",
        Rarity.UNCOMMON,
        IngredientCategory.HERB,
        True,
        EV.from_dict({"fire": 4}),
    )
    combo = Combination(picks=(Pick(double, 1),))
    read = read_as_portions(combo, EV.from_dict({"fire": 2}))
    assert read.portions == 2
    assert read.excess.is_empty


def test_single_portion_by_default(
    ingredients: dict[str, Ingredient], potions: dict[str, Potion]
) -> None:
    """С прежними значениями подбор не ищет ни лишнего, ни лишних порций."""
    stock = stock_from(ingredients, {"shcholkorekh": 4})
    rows = brewable(potions.values(), stock, [Kit.ALCHEMIST])
    fire = next(r for r in rows if r.potion.id == "alkhimicheskiy-ogon")
    assert all(o.portions == 1 and o.combination.is_exact for o in fire.options)


def test_portions_raise_difficulty(
    ingredients: dict[str, Ingredient], potions: dict[str, Potion]
) -> None:
    stock = stock_from(ingredients, {"shcholkorekh": 4})
    rows = brewable(potions.values(), stock, [Kit.ALCHEMIST], max_portions=2)
    fire = next(r for r in rows if r.potion.id == "alkhimicheskiy-ogon")
    by_portions = {o.portions: o.difficulty.total for o in fire.options}
    assert by_portions[1] == 10
    assert by_portions[2] == 12


def test_easiest_option_has_lowest_difficulty(
    ingredients: dict[str, Ingredient], potions: dict[str, Potion]
) -> None:
    stock = stock_from(ingredients, {"shcholkorekh": 4, "krov-drakocherepakhi": 2})
    rows = brewable(potions.values(), stock, [Kit.ALCHEMIST], max_excess=2, max_portions=2)
    fire = next(r for r in rows if r.potion.id == "alkhimicheskiy-ogon")
    assert fire.easiest.difficulty.total == min(o.difficulty.total for o in fire.options)
    assert fire.easiest.difficulty.total == 10


@pytest.mark.parametrize("kit", [Kit.ALCHEMIST, Kit.HERBALIST])
def test_kits_still_limit_excess_search(
    ingredients: dict[str, Ingredient], potions: dict[str, Potion], kit: Kit
) -> None:
    """П-6.3 никуда не делось: травнику эссенции и взрывная основа по-прежнему закрыты."""
    stock = stock_from(ingredients, {"tusklaya-essentsiya-ognya": 2, "shcholkorekh": 1})
    rows = brewable(potions.values(), stock, [kit], max_excess=3, max_portions=2)
    used = {p.ingredient.id for row in rows for o in row.options for p in o.combination.picks}
    if kit is Kit.HERBALIST:
        assert "tusklaya-essentsiya-ognya" not in used
    else:
        assert "tusklaya-essentsiya-ognya" in used
