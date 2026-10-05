from __future__ import annotations

from alchimist.core.elements import ElementVector as EV
from alchimist.core.errors import WarningCode
from alchimist.core.models import (
    ALL_BASES,
    BaseType,
    Ingredient,
    IngredientCategory,
    Kit,
    Potion,
    PotionKind,
    Rarity,
    Recipe,
)
from alchimist.core.rules import (
    build_recipe_index,
    check_catalog,
    check_ingredient,
    check_recipe,
    kit_allows_base,
    kit_allows_ingredient,
    kit_allows_potion,
)


def codes(messages: list) -> set[str]:
    return {m.code for m in messages}


def test_rarity_units_rule(ingredients: dict[str, Ingredient]) -> None:
    """П-3.2: единиц у реагента = его редкость."""
    ok = ingredients["semya-nochnogo-plameni"]  # редкий, 3 единицы
    assert check_ingredient(ok) == []

    bad = ok.copy(elements=EV.from_dict({"dark": 2}))
    messages = check_ingredient(bad)
    assert codes(messages) == {WarningCode.RARITY_UNITS_MISMATCH}
    assert messages[0].params == {"name": ok.name, "expected": 3, "actual": 2}


def test_recipe_size_rule(potions: dict[str, Potion]) -> None:
    """П-5.2: единиц в рецепте = редкость + 1. Необычное зелье с 2 единицами — предупреждение."""
    p = potions["plamya-salamandry"]  # необычное, 3 единицы — норма
    assert check_recipe(p, p.recipe, {}) == []

    small = Recipe(frozenset({BaseType.VISCOUS}), EV.from_dict({"fire": 2}))
    messages = check_recipe(p, small, {})
    assert codes(messages) == {WarningCode.RECIPE_SIZE_MISMATCH}
    assert messages[0].params["expected"] == 3
    assert messages[0].params["actual"] == 2


def test_recipe_collision(potions: dict[str, Potion]) -> None:
    """П-5.6: второй рецепт (liquid, {earth:2}) сталкивается с Зельем Лазанья."""
    index = build_recipe_index(potions.values())
    names = {p.id: p.name for p in potions.values()}
    newcomer = Potion(id="novoe", name="Новое зелье", rarity=Rarity.COMMON)
    recipe = Recipe(frozenset({BaseType.LIQUID}), EV.from_dict({"earth": 2}))

    messages = check_recipe(newcomer, recipe, index, names)
    assert codes(messages) == {WarningCode.RECIPE_COLLISION}
    assert messages[0].params["others"] == ["Зелье Лазанья"]
    assert messages[0].params["base"] == "liquid"


def test_no_collision_on_different_base(potions: dict[str, Potion]) -> None:
    """П-5.5: основа различает рецепты, {earth:2} на вязкой — это Зелье Пищеварения."""
    index = build_recipe_index(potions.values())
    newcomer = Potion(id="novoe", name="Новое", rarity=Rarity.COMMON)
    recipe = Recipe(frozenset({BaseType.EXPLOSIVE}), EV.from_dict({"earth": 2}))
    assert check_recipe(newcomer, recipe, index, {}) == []


def test_editing_own_recipe_is_not_a_collision(potions: dict[str, Potion]) -> None:
    index = build_recipe_index(potions.values())
    p = potions["zele-lazanya"]
    assert check_recipe(p, p.recipe, index, {}) == []


def test_catalog_check_reports_each_collision_once(potions: dict[str, Potion]) -> None:
    items = list(potions.values())
    twin = Potion(
        id="dvoynik",
        name="Двойник Лазаньи",
        rarity=Rarity.COMMON,
        recipe=Recipe(frozenset({BaseType.LIQUID}), EV.from_dict({"earth": 2})),
    )
    messages = check_catalog([], [*items, twin])
    collisions = [m for m in messages if m.code is WarningCode.RECIPE_COLLISION]
    assert len(collisions) == 1


def test_herbalist_kit(ingredients: dict[str, Ingredient], potions: dict[str, Potion]) -> None:
    """П-6.3: травник — только «Травы», только жидкая и вязкая основа."""
    herb = ingredients["shcholkorekh"]
    essence = ingredients["tusklaya-essentsiya-ognya"]
    creature = ingredients["krov-drakocherepakhi"]

    assert kit_allows_ingredient(Kit.HERBALIST, herb)
    assert not kit_allows_ingredient(Kit.HERBALIST, essence)
    assert not kit_allows_ingredient(Kit.HERBALIST, creature)
    assert kit_allows_ingredient(Kit.ALCHEMIST, essence)

    assert kit_allows_base(Kit.HERBALIST, BaseType.LIQUID)
    assert kit_allows_base(Kit.HERBALIST, BaseType.VISCOUS)
    assert not kit_allows_base(Kit.HERBALIST, BaseType.EXPLOSIVE)

    assert kit_allows_potion(Kit.HERBALIST, potions["alkhimicheskiy-ogon"])


def test_poisoner_kit(potions: dict[str, Potion]) -> None:
    """П-6.3: отравитель — только яды, основы любые [Допущение]."""
    poison = potions["zele-bezobraznoy-ploti"]
    ordinary = potions["alkhimicheskiy-ogon"]
    assert poison.kind is PotionKind.POISON
    assert kit_allows_potion(Kit.POISONER, poison)
    assert not kit_allows_potion(Kit.POISONER, ordinary)
    assert all(kit_allows_base(Kit.POISONER, b) for b in ALL_BASES)


def test_plants_are_herbs_by_default() -> None:
    plant = Ingredient(
        id="x",
        name="Сок",
        rarity=Rarity.UNCOMMON,
        category=IngredientCategory.PLANT,
        is_herb=True,
        elements=EV.from_dict({"earth": 2}),
    )
    assert kit_allows_ingredient(Kit.HERBALIST, plant)
