"""Модели приводят поля к своим типам, кто бы их ни создавал."""

from __future__ import annotations

from alchimist.core.elements import ElementVector as EV
from alchimist.core.models import (
    ALL_BASES,
    BaseType,
    BrewResult,
    Ingredient,
    IngredientCategory,
    JournalEntry,
    JournalEntryType,
    Outcome,
    Potion,
    PotionKind,
    Rarity,
    Recipe,
    ResultKind,
    coerce_enum,
)
from alchimist.storage.serde import entry_to_dict, ingredient_to_dict, potion_to_dict


def test_coerce_enum() -> None:
    assert coerce_enum(BaseType, "liquid") is BaseType.LIQUID
    assert coerce_enum(BaseType, BaseType.VISCOUS) is BaseType.VISCOUS
    assert coerce_enum(BaseType, None) is None
    assert coerce_enum(BaseType, "нет такого") is None
    assert coerce_enum(Rarity, 3) is Rarity.RARE


def test_ingredient_from_plain_values() -> None:
    """Qt возвращает из виджетов обычные str и int, а не сами enum'ы."""
    ingredient = Ingredient(
        id="x", name="X", rarity=3, category="essence", elements=EV.from_dict({"fire": 3})
    )
    assert ingredient.rarity is Rarity.RARE
    assert ingredient.category is IngredientCategory.ESSENCE
    assert ingredient_to_dict(ingredient)["category"] == "essence"


def test_potion_and_recipe_from_plain_values() -> None:
    potion = Potion(
        id="x",
        name="X",
        rarity=2,
        kind="poison",
        recipe=Recipe(frozenset({"liquid", "viscous"}), EV.from_dict({"fire": 3})),
    )
    assert potion.rarity is Rarity.UNCOMMON
    assert potion.kind is PotionKind.POISON
    assert potion.recipe.bases == frozenset({BaseType.LIQUID, BaseType.VISCOUS})
    assert potion_to_dict(potion)["recipe"]["bases"] == ["liquid", "viscous"]


def test_journal_entry_from_plain_values() -> None:
    from datetime import datetime

    entry = JournalEntry(
        id="x",
        ts=datetime.now().astimezone(),
        type="brew",
        base="explosive",
        outcome="success",
        result=BrewResult("known", "p"),
        elements=EV.from_dict({"fire": 2}),
    )
    assert entry.type is JournalEntryType.BREW
    assert entry.base is BaseType.EXPLOSIVE
    assert entry.outcome is Outcome.SUCCESS
    assert entry.result.kind is ResultKind.KNOWN
    assert entry_to_dict(entry)["base"] == "explosive"


def test_recipe_drops_unknown_bases() -> None:
    recipe = Recipe(frozenset({"liquid", "gaseous"}), EV.from_dict({"fire": 2}))
    assert recipe.bases == frozenset({BaseType.LIQUID})


def test_any_base_formatting() -> None:
    assert Recipe(ALL_BASES, EV.from_dict({"fire": 2})).format_bases_ru() == "Любая"
