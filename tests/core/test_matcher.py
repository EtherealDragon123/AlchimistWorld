from __future__ import annotations

from alchimist.core.elements import ElementVector as EV
from alchimist.core.matcher import (
    StockItem,
    almost_ready,
    best_subset,
    brewable,
    find_combinations,
    find_fillers,
    stock_from,
)
from alchimist.core.models import BaseType, Ingredient, Kit, Potion


def names(combination) -> list[tuple[str, int]]:
    return sorted((p.ingredient.name, p.count) for p in combination.picks)


def make_stock(ingredients: dict[str, Ingredient], **qty: int) -> list[StockItem]:
    return stock_from(ingredients, qty)


# ── П-5.3 Правило суммы, П-5.4 Точное совпадение ─────────────────────────────
def test_sum_rule_two_herbs(ingredients: dict[str, Ingredient]) -> None:
    """Щёлкорех×2 → {fire:2}."""
    stock = make_stock(ingredients, shcholkorekh=2)
    combos = find_combinations(EV.from_dict({"fire": 2}), stock)
    assert len(combos) == 1
    assert names(combos[0]) == [("Щёлкорех", 2)]


def test_one_essence_instead_of_two_herbs(ingredients: dict[str, Ingredient]) -> None:
    """Одна Тусклая эссенция огня даёт те же {fire:2}."""
    stock = make_stock(ingredients, tusklaya_essentsiya_ognya=1)
    stock = stock_from(ingredients, {"tusklaya-essentsiya-ognya": 1})
    combos = find_combinations(EV.from_dict({"fire": 2}), stock)
    assert names(combos[0]) == [("Тусклая эссенция огня", 1)]


def test_extra_element_never_fits(ingredients: dict[str, Ingredient]) -> None:
    """Кровь дракочерепахи ({water:2, fire:1}) не годится для {fire:2}."""
    stock = stock_from(ingredients, {"krov-drakocherepakhi": 3})
    assert find_combinations(EV.from_dict({"fire": 2}), stock) == []


def test_reagent_gives_all_its_elements(ingredients: dict[str, Ingredient]) -> None:
    """П-3.4: из Семени ночного пламени нельзя взять только Огонь."""
    stock = stock_from(ingredients, {"semya-nochnogo-plameni": 2})
    assert find_combinations(EV.from_dict({"fire": 1}), stock) == []
    assert find_combinations(EV.from_dict({"dark": 2, "fire": 1}), stock)


def test_interchangeable_reagents_are_one_class(ingredients: dict[str, Ingredient]) -> None:
    """Сопли Тролля и Мертвостой — оба {water:1}, класс один, вариант тоже один."""
    stock = stock_from(ingredients, {"sopli-trollya": 1, "mertvostoy": 1})
    combos = find_combinations(EV.from_dict({"water": 2}), stock)
    assert len(combos) == 1
    assert names(combos[0]) == [("Мертвостой", 1), ("Сопли Тролля", 1)]


def test_cheapest_option_comes_first(ingredients: dict[str, Ingredient]) -> None:
    """FR-5.2: две обычных травы дешевле одной необычной эссенции."""
    stock = stock_from(ingredients, {"shcholkorekh": 2, "tusklaya-essentsiya-ognya": 1})
    combos = find_combinations(EV.from_dict({"fire": 2}), stock)
    assert names(combos[0]) == [("Щёлкорех", 2)]
    assert names(combos[1]) == [("Тусклая эссенция огня", 1)]
    assert combos[0].cost < combos[1].cost


def test_repeats(ingredients: dict[str, Ingredient]) -> None:
    """FR-5.3: 5 Щёлкорехов на рецепт из двух → три варки."""
    stock = stock_from(ingredients, {"shcholkorekh": 5})
    combo = find_combinations(EV.from_dict({"fire": 2}), stock)[0]
    assert combo.repeats == 2


# ── П-5.5 Основа различает рецепты ───────────────────────────────────────────
def test_base_distinguishes_recipes(
    ingredients: dict[str, Ingredient], potions: dict[str, Potion]
) -> None:
    """{earth:1, fire:1}: жидкая → Сила Огра, взрывная → Динамит."""
    stock = stock_from(ingredients, {"shcholkorekh": 1, "tkanevyy-list": 1})
    rows = brewable(potions.values(), stock, [Kit.ALCHEMIST])
    by_id = {r.potion.id: r for r in rows}

    assert by_id["zele-sily-ogra"].best.base is BaseType.LIQUID
    assert by_id["dinamit"].best.base is BaseType.EXPLOSIVE


def test_any_base_is_one_option(
    ingredients: dict[str, Ingredient], potions: dict[str, Potion]
) -> None:
    """Алхимический Огонь варится на любой основе (П-5.1).

    Один и тот же набор реагентов — один вариант с тремя допустимыми основами,
    а не три почти одинаковых строки: основу игрок выбирает в диалоге варки.
    """
    stock = stock_from(ingredients, {"shcholkorekh": 2})
    rows = {r.potion.id: r for r in brewable(potions.values(), stock, [Kit.ALCHEMIST])}
    options = rows["alkhimicheskiy-ogon"].options
    assert len(options) == 1
    assert options[0].bases == {BaseType.LIQUID, BaseType.VISCOUS, BaseType.EXPLOSIVE}
    assert options[0].format_bases_ru() == "Любая"
    assert options[0].base is BaseType.LIQUID  # по умолчанию — первая по порядку


def test_unknown_recipe_never_brewable(
    ingredients: dict[str, Ingredient], potions: dict[str, Potion]
) -> None:
    """П-5.7: Бармаглот без рецепта в подборе не участвует."""
    stock = stock_from(ingredients, dict.fromkeys(ingredients, 5))
    rows = brewable(potions.values(), stock, [Kit.ALCHEMIST])
    assert "barmaglot" not in {r.potion.id for r in rows}


# ── П-6.3 Наборы ─────────────────────────────────────────────────────────────
def test_herbalist_excludes_essences_and_explosive(
    ingredients: dict[str, Ingredient], potions: dict[str, Potion]
) -> None:
    stock = stock_from(ingredients, {"tusklaya-essentsiya-ognya": 1, "tkanevyy-list": 2})
    rows = {r.potion.id: r for r in brewable(potions.values(), stock, [Kit.HERBALIST])}
    # Эссенция травнику недоступна → Алхимический Огонь не варится.
    assert "alkhimicheskiy-ogon" not in rows
    # Земля×2 из трав — можно, но только на жидкой и вязкой основе.
    assert {o.base for o in rows["zele-lazanya"].options} == {BaseType.LIQUID}

    explosive_only = stock_from(ingredients, {"shcholkorekh": 1, "podlunnukh": 1})
    rows2 = {r.potion.id: r for r in brewable(potions.values(), explosive_only, [Kit.HERBALIST])}
    assert "kislota" not in rows2  # Кислота только на взрывной основе


def test_poisoner_only_poisons(
    ingredients: dict[str, Ingredient], potions: dict[str, Potion]
) -> None:
    stock = stock_from(ingredients, dict.fromkeys(ingredients, 5))
    rows = brewable(potions.values(), stock, [Kit.POISONER])
    assert {r.potion.kind.value for r in rows} == {"poison"}


def test_kits_do_not_mix_in_one_brew(potions: dict[str, Potion]) -> None:
    """03 §4.3: травы по праву травника и эссенцию по праву отравителя не смешать."""
    from alchimist.core.models import IngredientCategory, Rarity

    herb = Ingredient(
        "herb-fire",
        "Огненная трава",
        Rarity.COMMON,
        IngredientCategory.PLANT,
        EV.from_dict({"fire": 1}),
    )
    essence = Ingredient(
        "ess-water",
        "Эссенция воды",
        Rarity.COMMON,
        IngredientCategory.ESSENCE,
        EV.from_dict({"water": 1}),
    )
    poison = Potion(
        id="mix-poison",
        name="Смешанный яд",
        rarity=Rarity.COMMON,
        kind=__import__("alchimist.core.models", fromlist=["PotionKind"]).PotionKind.POISON,
        recipe=__import__("alchimist.core.models", fromlist=["Recipe"]).Recipe(
            frozenset({BaseType.VISCOUS}), EV.from_dict({"fire": 1, "water": 1})
        ),
    )
    stock = [StockItem(herb, 1), StockItem(essence, 1)]

    # Травник: эссенция недоступна. Отравитель: доступно всё, но только яды.
    assert brewable([poison], stock, [Kit.HERBALIST]) == []
    assert len(brewable([poison], stock, [Kit.POISONER])) == 1
    # Оба набора сразу — вариант находит отравитель целиком, а не половинками.
    both = brewable([poison], stock, [Kit.HERBALIST, Kit.POISONER])
    assert len(both) == 1
    assert both[0].best.kit is Kit.POISONER


# ── §5.4 «Почти готово» ──────────────────────────────────────────────────────
def test_almost_ready(ingredients: dict[str, Ingredient], potions: dict[str, Potion]) -> None:
    """03 §9: Щёлкорех×2 → Пламени Саламандры не хватает Свет×1."""
    stock = stock_from(ingredients, {"shcholkorekh": 2})
    rows = almost_ready(
        potions.values(),
        stock,
        [Kit.ALCHEMIST],
        ingredients.values(),
        brewable_ids=[r.potion.id for r in brewable(potions.values(), stock, [Kit.ALCHEMIST])],
    )
    row = next(r for r in rows if r.potion.id == "plamya-salamandry")
    assert row.missing.to_dict() == {"light": 1}
    assert row.base is BaseType.VISCOUS
    assert names(row.have) == [("Щёлкорех", 2)]

    filler_names = {p.ingredient.name for f in row.fillers for p in f.picks}
    assert filler_names == {"Свечная Роза", "Мыльная Трава", "Фосфорицирующая эссенция света"}


def test_almost_ready_sorted_by_missing(
    ingredients: dict[str, Ingredient], potions: dict[str, Potion]
) -> None:
    stock = stock_from(ingredients, {"shcholkorekh": 2})
    rows = almost_ready(potions.values(), stock, [Kit.ALCHEMIST], ingredients.values())
    assert [r.missing_units for r in rows] == sorted(r.missing_units for r in rows)


def test_best_subset_picks_the_largest_fitting_sum(ingredients: dict[str, Ingredient]) -> None:
    stock = stock_from(ingredients, {"shcholkorekh": 4, "svechnaya-roza": 1})
    have = best_subset(EV.from_dict({"fire": 2, "light": 1}), stock)
    assert have.elements.to_dict() == {"fire": 2, "light": 1}


def test_fillers_never_exceed_two_reagents(ingredients: dict[str, Ingredient]) -> None:
    fillers = find_fillers(EV.from_dict({"fire": 2}), ingredients.values())
    assert fillers
    assert all(f.count <= 2 for f in fillers)
    # Самый простой вариант — один реагент — идёт первым.
    assert fillers[0].count == 1
