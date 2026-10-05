"""Маленький набор реальных данных из заметок — общая фикстура тестов."""

from __future__ import annotations

import pytest

from alchimist.core.elements import ElementVector as EV
from alchimist.core.models import (
    ALL_BASES,
    BaseType,
    Catalog,
    Ingredient,
    IngredientCategory,
    Potion,
    PotionKind,
    Rarity,
    Recipe,
)


def ing(
    ident: str,
    name: str,
    rarity: Rarity,
    category: IngredientCategory,
    elements: dict[str, int],
    *,
    is_herb: bool | None = None,
) -> Ingredient:
    if is_herb is None:
        is_herb = category in (IngredientCategory.HERB, IngredientCategory.PLANT)
    return Ingredient(
        id=ident,
        name=name,
        rarity=rarity,
        category=category,
        is_herb=is_herb,
        elements=EV.from_dict(elements),
    )


def potion(
    ident: str,
    name: str,
    rarity: Rarity,
    bases: set[BaseType] | None,
    elements: dict[str, int] | None,
    *,
    kind: PotionKind = PotionKind.POTION,
    family: str | None = None,
) -> Potion:
    recipe = None
    if bases is not None and elements is not None:
        recipe = Recipe(frozenset(bases), EV.from_dict(elements))
    return Potion(id=ident, name=name, rarity=rarity, kind=kind, family=family, recipe=recipe)


# ── Реагенты из Алхимия/Ингридиенты ──────────────────────────────────────────
H = IngredientCategory.HERB
P = IngredientCategory.PLANT
E = IngredientCategory.ESSENCE
C = IngredientCategory.CREATURE


@pytest.fixture
def ingredients() -> dict[str, Ingredient]:
    items = [
        ing("shcholkorekh", "Щёлкорех", Rarity.COMMON, H, {"fire": 1}),
        ing("svechnaya-roza", "Свечная Роза", Rarity.COMMON, H, {"light": 1}),
        ing("mylnaya-trava", "Мыльная Трава", Rarity.COMMON, H, {"light": 1}),
        ing("podlunnukh", "Подлуннух", Rarity.COMMON, H, {"dark": 1}),
        ing("mogilnaya-loza", "Могильная Лоза", Rarity.COMMON, H, {"dark": 1}),
        ing("sopli-trollya", "Сопли Тролля", Rarity.COMMON, H, {"water": 1}),
        ing("mertvostoy", "Мертвостой", Rarity.COMMON, H, {"water": 1}),
        ing("tkanevyy-list", "Тканевый лист", Rarity.COMMON, H, {"earth": 1}),
        ing("fanana", "Фанана", Rarity.COMMON, H, {"air": 1}),
        ing(
            "fosforitsiruyushchaya-essentsiya-sveta",
            "Фосфорицирующая эссенция света",
            Rarity.COMMON,
            E,
            {"light": 1},
        ),
        ing(
            "tusklaya-essentsiya-ognya",
            "Тусклая эссенция огня",
            Rarity.UNCOMMON,
            E,
            {"fire": 2},
        ),
        ing("ledyanaya-loza", "Ледяная лоза", Rarity.UNCOMMON, P, {"water": 1, "magic": 1}),
        ing("sok-stalnogo-dereva", "Сок Стального Дерева", Rarity.UNCOMMON, P, {"earth": 2}),
        ing(
            "semya-nochnogo-plameni", "Семя ночного пламени", Rarity.RARE, H, {"dark": 2, "fire": 1}
        ),
        ing("krov-drakocherepakhi", "Кровь дракочерепахи", Rarity.RARE, C, {"water": 2, "fire": 1}),
    ]
    return {i.id: i for i in items}


@pytest.fixture
def potions() -> dict[str, Potion]:
    items = [
        potion("alkhimicheskiy-ogon", "Алхимический Огонь", Rarity.COMMON, ALL_BASES, {"fire": 2}),
        potion(
            "zele-lecheniya-slaboe",
            "Зелье Лечения (Слабое)",
            Rarity.COMMON,
            {BaseType.LIQUID, BaseType.VISCOUS},
            {"dark": 1, "light": 1},
            family="Зелье Лечения",
        ),
        potion(
            "zele-sily-ogra",
            "Зелье Силы Огра",
            Rarity.COMMON,
            {BaseType.LIQUID},
            {"earth": 1, "fire": 1},
        ),
        potion("dinamit", "Динамит", Rarity.COMMON, {BaseType.EXPLOSIVE}, {"earth": 1, "fire": 1}),
        potion("zele-lazanya", "Зелье Лазанья", Rarity.COMMON, {BaseType.LIQUID}, {"earth": 2}),
        potion(
            "zele-pishchevareniya",
            "Зелье Пищеварения",
            Rarity.COMMON,
            {BaseType.VISCOUS},
            {"earth": 2},
        ),
        potion(
            "zele-bezobraznoy-ploti",
            "Зелье Безобразной Плоти",
            Rarity.COMMON,
            {BaseType.LIQUID},
            {"dark": 1, "earth": 1},
            kind=PotionKind.POISON,
        ),
        potion(
            "kislota",
            "Кислота",
            Rarity.COMMON,
            {BaseType.EXPLOSIVE},
            {"dark": 1, "earth": 1},
        ),
        potion(
            "plamya-salamandry",
            "Пламя Саламандры",
            Rarity.UNCOMMON,
            {BaseType.VISCOUS},
            {"fire": 2, "light": 1},
        ),
        potion(
            "obychnyy-yad",
            "Обычный Яд",
            Rarity.COMMON,
            {BaseType.VISCOUS},
            {"water": 1, "dark": 1},
            kind=PotionKind.POISON,
        ),
        potion("barmaglot", "Бармаглот", Rarity.UNCOMMON, None, None),
    ]
    return {p.id: p for p in items}


@pytest.fixture
def catalog(ingredients: dict[str, Ingredient], potions: dict[str, Potion]) -> Catalog:
    return Catalog(list(ingredients.values()), list(potions.values()))
