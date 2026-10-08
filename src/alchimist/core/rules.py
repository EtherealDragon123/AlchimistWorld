"""Проверки правил и разрешения наборов (П-3.2, П-5.2, П-5.6, П-6.3)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from alchimist.core.elements import ElementVector
from alchimist.core.errors import Message, WarningCode, warning
from alchimist.core.models import (
    ALL_BASES,
    BaseKey,
    BaseType,
    Ingredient,
    Kit,
    Potion,
    PotionKind,
    Rarity,
    Recipe,
    is_special_base_key,
)

#: Основа (тип или особая) и сумма элементов — по этой паре рецепты не должны совпадать.
RecipeKey = tuple[BaseKey, ElementVector]

#: Какие основы разрешает набор (П-6.3).
KIT_BASES: dict[Kit, frozenset[BaseType]] = {
    Kit.ALCHEMIST: ALL_BASES,
    # Травник варит только на жидкой и вязкой основе.
    Kit.HERBALIST: frozenset({BaseType.LIQUID, BaseType.VISCOUS}),
    # [Допущение] Отравитель не ограничен по основам (вопрос 4 к DM).
    Kit.POISONER: ALL_BASES,
}


# ── Разрешения наборов ────────────────────────────────────────────────────────
def kit_allows_base(kit: Kit, base: BaseKey) -> bool:
    """Особая основа доступна любому набору, в том числе травнику (П-4.4)."""
    if is_special_base_key(base):
        return True
    return base in KIT_BASES[kit]


def kit_allows_ingredient(kit: Kit, ingredient: Ingredient) -> bool:
    """Травник работает только с растениями (П-3.3, П-6.3)."""
    if kit is Kit.HERBALIST:
        return ingredient.is_plant
    return True


def kit_allows_potion(kit: Kit, potion: Potion) -> bool:
    """Отравитель делает только яды (П-6.3)."""
    if kit is Kit.POISONER:
        return potion.kind is PotionKind.POISON
    return True


# ── П-3.2: число единиц реагента = его редкость ──────────────────────────────
def check_ingredient(ingredient: Ingredient) -> list[Message]:
    """Предупреждения по реагенту. Сохранению не мешают (FR-1.4).

    У особой основы единиц на одну меньше редкости (П-4.4): редкая — два элемента.
    Без элементов не бывает ни реагента, ни особой основы.
    """
    messages: list[Message] = []
    total = ingredient.elements.total
    expected = ingredient.expected_units()
    if total == 0:
        messages.append(warning(WarningCode.INGREDIENT_NO_ELEMENTS, name=ingredient.name))
    elif total != expected:
        messages.append(
            warning(
                WarningCode.RARITY_UNITS_MISMATCH,
                name=ingredient.name,
                expected=expected,
                actual=total,
            )
        )
    return messages


# ── П-5.2: число единиц рецепта = редкость зелья + 1 ─────────────────────────
def expected_recipe_units(potion: Potion) -> int:
    return int(potion.rarity) + 1


def check_recipe_size(potion: Potion, recipe: Recipe) -> list[Message]:
    messages: list[Message] = []
    # У рецепта на особой основе обычных основ нет и быть не должно (П-4.4).
    if not recipe.bases and not recipe.required_base_id:
        messages.append(warning(WarningCode.RECIPE_NO_BASES, name=potion.name))
    total = recipe.elements.total
    if total == 0:
        messages.append(warning(WarningCode.RECIPE_NO_ELEMENTS, name=potion.name))
        return messages
    expected = expected_recipe_units(potion)
    if total != expected:
        messages.append(
            warning(
                WarningCode.RECIPE_SIZE_MISMATCH,
                name=potion.name,
                expected=expected,
                actual=total,
            )
        )
    return messages


# ── П-5.6: индекс рецептов и коллизии ────────────────────────────────────────
def build_recipe_index(potions: Iterable[Potion]) -> dict[RecipeKey, set[str]]:
    """Ключ (основа, элементы) → id зелий. Рецепт с N основами занимает N ключей."""
    index: dict[RecipeKey, set[str]] = {}
    for potion in potions:
        if potion.recipe is None:
            continue
        for key in potion.recipe.index_keys():
            index.setdefault(key, set()).add(potion.id)
    return index


def find_collisions(
    index: Mapping[RecipeKey, set[str]],
    potion_id: str,
    recipe: Recipe,
) -> dict[BaseKey, set[str]]:
    """Какие основы рецепта конфликтуют и с какими зельями (кроме самого зелья)."""
    collisions: dict[BaseKey, set[str]] = {}
    for base, elements in recipe.index_keys():
        others = {pid for pid in index.get((base, elements), set()) if pid != potion_id}
        if others:
            collisions[base] = others
    return collisions


def check_recipe(
    potion: Potion,
    recipe: Recipe,
    index: Mapping[RecipeKey, set[str]],
    names: Mapping[str, str] | None = None,
    base_names: Mapping[str, str] | None = None,
) -> list[Message]:
    """Полная проверка рецепта по П-5.6: коллизия + размер.

    `names` — id зелья → название, `base_names` — id особой основы → название:
    чтобы предупреждение о коллизии несло читаемые имена.
    """
    messages = check_recipe_size(potion, recipe)
    names = names or {}
    for base, others in find_collisions(index, potion.id, recipe).items():
        special = is_special_base_key(base)
        messages.append(
            warning(
                WarningCode.RECIPE_COLLISION,
                name=potion.name,
                base=str(base),
                base_name=(base_names or {}).get(str(base), str(base)) if special else None,
                others=sorted(names.get(pid, pid) for pid in others),
                other_ids=sorted(others),
            )
        )
    return messages


def check_catalog(
    ingredients: Iterable[Ingredient],
    potions: Iterable[Potion],
) -> list[Message]:
    """Проверки П-3.2, П-5.2 и П-5.6 над всем каталогом (нужно после обмена, 03 §6.9)."""
    ingredients = list(ingredients)
    potions = list(potions)
    messages: list[Message] = []
    for ingredient in ingredients:
        messages.extend(check_ingredient(ingredient))
    index = build_recipe_index(potions)
    names = {p.id: p.name for p in potions}
    seen_pairs: set[tuple[str, ...]] = set()
    for potion in potions:
        if potion.recipe is None:
            continue
        for message in check_recipe(potion, potion.recipe, index, names):
            if message.code is WarningCode.RECIPE_COLLISION:
                # Коллизия симметрична: сообщаем о каждой паре один раз.
                pair = (
                    *sorted([potion.id, *message.params["other_ids"]]),
                    message.params["base"],
                )
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
            messages.append(message)
    return messages


# ── П-8: сложность приготовления ─────────────────────────────────────────────
#: Обычное зелье без лишнего и в одну порцию.
BASE_DIFFICULTY = 10
#: Каждый ранг редкости: обычное +0, необычное +2, редкое +4, эпическое +6, легендарное +8.
RARITY_STEP = 2
#: Каждая порция сверх первой (П-8.2).
PORTION_STEP = 2
#: Каждая лишняя единица элемента (П-8.1).
EXCESS_STEP = 1


@dataclass(frozen=True, slots=True)
class Difficulty:
    """Сложность проверки алхимии для одной варки (П-8).

    Итог складывается так: 10 + [редкость] + [порции] + [лишние эссенции].
    Слагаемые хранятся отдельно, чтобы интерфейс показывал разбор, а не число.
    """

    rarity: Rarity = Rarity.COMMON
    portions: int = 1
    excess_units: int = 0

    @property
    def base(self) -> int:
        return BASE_DIFFICULTY

    @property
    def rarity_penalty(self) -> int:
        return RARITY_STEP * (int(self.rarity) - 1)

    @property
    def portion_penalty(self) -> int:
        return PORTION_STEP * (max(1, self.portions) - 1)

    @property
    def excess_penalty(self) -> int:
        return EXCESS_STEP * max(0, self.excess_units)

    @property
    def total(self) -> int:
        return self.base + self.rarity_penalty + self.portion_penalty + self.excess_penalty

    def parts(self) -> list[tuple[str, int]]:
        """Слагаемые с подписями — для подсказки «10 + 6 + 2 + 1 = 19»."""
        return [
            ("base", self.base),
            ("rarity", self.rarity_penalty),
            ("portions", self.portion_penalty),
            ("excess", self.excess_penalty),
        ]

    def format_ru(self) -> str:
        return " + ".join(str(value) for _name, value in self.parts()) + f" = {self.total}"


def brew_difficulty(rarity: Rarity, portions: int = 1, excess_units: int = 0) -> Difficulty:
    return Difficulty(Rarity(rarity), max(1, portions), max(0, excess_units))
