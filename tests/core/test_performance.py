from __future__ import annotations

import os
import random
import time

from alchimist.core.elements import ELEMENT_ORDER
from alchimist.core.elements import ElementVector as EV
from alchimist.core.matcher import StockItem, almost_ready, brewable
from alchimist.core.models import (
    ALL_BASES,
    Ingredient,
    IngredientCategory,
    Kit,
    Potion,
    Rarity,
    Recipe,
)

#: Машины CI заметно медленнее рабочей: там лимиты времени втрое мягче.
#: Замедление алгоритма в разы это всё равно ловит.
SLOWDOWN = 3 if os.environ.get("CI") else 1


def _random_vector(rng: random.Random, units: int) -> EV:
    return EV.from_elements(rng.choice(ELEMENT_ORDER) for _ in range(units))


def _dataset() -> tuple[list[Ingredient], list[Potion], list[StockItem]]:
    rng = random.Random(20260911)
    ingredients: list[Ingredient] = []
    for i in range(500):
        rarity = Rarity(rng.randint(1, 5))
        ingredients.append(
            Ingredient(
                id=f"ing-{i}",
                name=f"Реагент {i}",
                rarity=rarity,
                category=rng.choice(list(IngredientCategory)),
                elements=_random_vector(rng, int(rarity)),
            )
        )
    potions = [
        Potion(
            id=f"pot-{i}",
            name=f"Зелье {i}",
            rarity=(r := Rarity(rng.randint(1, 5))),
            recipe=Recipe(ALL_BASES, _random_vector(rng, int(r) + 1)),
        )
        for i in range(300)
    ]
    stock = [StockItem(ing, rng.randint(1, 4)) for ing in ingredients]
    return ingredients, potions, stock


def test_can_brew_under_200ms() -> None:
    """NFR-5: точный подбор для 500 реагентов и 300 рецептов — меньше 200 мс."""
    _, potions, stock = _dataset()
    start = time.perf_counter()
    rows = brewable(potions, stock, [Kit.ALCHEMIST])
    elapsed = time.perf_counter() - start
    assert rows
    assert elapsed < 0.2 * SLOWDOWN, f"подбор занял {elapsed * 1000:.0f} мс"


def test_brewing_with_excess_stays_bounded() -> None:
    """NFR-5: подбор с лишними эссенциями и порциями (П-8) шире точного.

    Точное совпадение укладывается в 200 мс, а покрытие с излишком перебирает
    заметно больше. Время всё равно ограничено потолками перебора, и здесь
    проверяется именно это: на предельных данных счёт не уходит в бесконечность.
    """
    _, potions, stock = _dataset()
    start = time.perf_counter()
    rows = brewable(potions, stock, [Kit.ALCHEMIST], max_excess=2, max_portions=3)
    elapsed = time.perf_counter() - start
    assert rows
    assert elapsed < 5.0 * SLOWDOWN, f"подбор с излишком занял {elapsed:.1f} с"


def test_real_scale_stays_fast(tmp_path, campaign_file) -> None:
    """На данных настоящей кампании полный подбор незаметен для глаза."""
    from alchimist.services import build_app

    app = build_app(tmp_path)
    app.exchange.apply(app.exchange.plan(campaign_file))
    stock = [StockItem(ingredient, 5) for ingredient in app.catalog.ingredients()]

    start = time.perf_counter()
    brewable(app.catalog.potions(), stock, [Kit.ALCHEMIST], max_excess=2, max_portions=3)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5 * SLOWDOWN, f"подбор занял {elapsed * 1000:.0f} мс"


def test_almost_ready_is_usable_on_the_same_dataset() -> None:
    ingredients, potions, stock = _dataset()
    start = time.perf_counter()
    rows = almost_ready(potions, stock, [Kit.ALCHEMIST], ingredients)
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0 * SLOWDOWN, f"«почти готово» заняло {elapsed * 1000:.0f} мс"
    assert all(r.missing.total > 0 for r in rows)
