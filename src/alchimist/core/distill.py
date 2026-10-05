"""Дистилляция: разбор реагентов на эссенции (П-9).

Реагенты кладутся в «Дистиллирующий Экстракт» и через несколько часов исчезают,
оставляя вместо себя эссенции — ту же самую магическую энергию, но в чистом виде.
Считается это по элементам, а не по реагентам: всё, что попало в экстракт,
складывается в одну сумму, и каждая стихия разбирается отдельно от остальных
(П-9.3). Обратная операция тоже есть: одинокая эссенция рассыпается на
фосфорицирующие (П-9.5).

Модуль не знает ни про справочник, ни про инвентарь: он считает, *что* выйдет,
а найти эти эссенции среди реагентов и списать потраченное — дело сервиса.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from alchimist.core.elements import ELEMENT_ORDER, Element, ElementVector
from alchimist.core.errors import ErrorCode, Message, Severity, error
from alchimist.core.models import Ingredient, IngredientCategory

#: П-9.1: больше пяти реагентов в экстракт не помещается.
MAX_REAGENTS = 5

#: Сильнее сияющей эссенции (5 единиц) не бывает — это потолок лестницы редкостей.
MAX_LEVEL = 5

#: Ниже этого уровня эссенцию уже не раздробить (П-9.5).
MIN_BREAKDOWN_LEVEL = 2

#: Как называется каждая ступень лестницы эссенций (П-9.2).
LEVEL_NAMES_RU: dict[int, str] = {
    1: "Фосфорицирующая",
    2: "Тусклая",
    3: "Сверкающая",
    4: "Светящаяся",
    5: "Сияющая",
}


#: Стихия в родительном падеже: «эссенция огня», а не «эссенция огонь».
ELEMENT_OF_RU: dict[Element, str] = {
    Element.FIRE: "огня",
    Element.WATER: "воды",
    Element.AIR: "воздуха",
    Element.EARTH: "земли",
    Element.LIGHT: "света",
    Element.DARK: "тьмы",
    Element.MAGIC: "магии",
}


def essence_name_ru(element: Element, level: int) -> str:
    """«Сияющая эссенция земли» — так эссенции названы в справочнике."""
    return f"{LEVEL_NAMES_RU.get(level, level)} эссенция {ELEMENT_OF_RU[element]}"


def essence_level(ingredient: Ingredient) -> int | None:
    """Уровень эссенции: 1 (фосфорицирующая) … 5 (сияющая).

    `None` — если это не эссенция одной стихии. По П-3.2 единиц в реагенте
    ровно столько, какова его редкость, так что уровень читается прямо из
    элементов и отдельного поля не требует.
    """
    if ingredient.category is not IngredientCategory.ESSENCE:
        return None
    items = list(ingredient.elements.items())
    if len(items) != 1:
        return None
    level = items[0][1]
    return level if 1 <= level <= MAX_LEVEL else None


def essence_element(ingredient: Ingredient) -> Element | None:
    """Стихия эссенции, если реагент — эссенция."""
    if essence_level(ingredient) is None:
        return None
    return next(iter(ingredient.elements.items()))[0]


@dataclass(frozen=True, slots=True)
class EssenceYield:
    """Сколько эссенций одного вида выйдет: стихия, уровень, штук."""

    element: Element
    level: int
    count: int = 1

    @property
    def units(self) -> int:
        """Сколько единиц элемента в этой стопке."""
        return self.level * self.count


@dataclass(frozen=True, slots=True)
class DistillPlan:
    """Что выйдет из экстракта и почему этого может не выйти вовсе."""

    elements: ElementVector = field(default_factory=ElementVector)
    yields: tuple[EssenceYield, ...] = ()
    #: Сколько реагентов лежит в экстракте — по П-9.1 их не больше пяти.
    reagents: int = 0
    #: Сработало П-9.5: одинокая эссенция рассыпалась на фосфорицирующие.
    broken_down: bool = False
    messages: tuple[Message, ...] = ()

    @property
    def errors(self) -> tuple[Message, ...]:
        return tuple(m for m in self.messages if m.severity is Severity.ERROR)

    @property
    def ok(self) -> bool:
        """Можно ли это разобрать на самом деле."""
        return bool(self.yields) and not self.errors

    @property
    def count(self) -> int:
        """Сколько эссенций выйдет всего."""
        return sum(y.count for y in self.yields)


def split_units(units: int) -> list[int]:
    """Разбивает единицы одной стихии по эссенциям (П-9.2).

    Берётся самая крупная эссенция, какая влезает, потом остаток: 7 единиц земли
    дают сияющую (5) и тусклую (2), а не, скажем, светящуюся и сверкающую.
    """
    if units <= 0:
        return []
    full, rest = divmod(units, MAX_LEVEL)
    return [MAX_LEVEL] * full + ([rest] if rest else [])


def distill_elements(elements: ElementVector) -> tuple[EssenceYield, ...]:
    """Обычная схема (П-9.2–П-9.4): каждая стихия разбирается сама по себе."""
    yields: list[EssenceYield] = []
    for element in ELEMENT_ORDER:
        units = elements[element]
        if not units:
            continue
        levels = split_units(units)
        # Одинаковые эссенции показываются одной стопкой: «сияющая ×2».
        for level in sorted(set(levels), reverse=True):
            yields.append(EssenceYield(element, level, levels.count(level)))
    return tuple(yields)


def break_down(element: Element, level: int) -> tuple[EssenceYield, ...]:
    """П-9.5: одинокая эссенция рассыпается на фосфорицирующие по числу единиц."""
    if level < MIN_BREAKDOWN_LEVEL:
        return ()
    return (EssenceYield(element, 1, level),)


def _as_essences(picked: Sequence[tuple[Ingredient, int]]) -> dict[tuple[Element, int], int] | None:
    """Вход как набор эссенций, или `None`, если там есть обычные реагенты."""
    out: dict[tuple[Element, int], int] = {}
    for ingredient, qty in picked:
        level = essence_level(ingredient)
        element = essence_element(ingredient)
        if level is None or element is None:
            return None
        out[(element, level)] = out.get((element, level), 0) + qty
    return out


def plan_distillation(items: Sequence[tuple[Ingredient, int]]) -> DistillPlan:
    """Считает разбор для набора «реагент → сколько штук» (П-9)."""
    picked = [(ingredient, qty) for ingredient, qty in items if qty > 0]
    reagents = sum(qty for _i, qty in picked)
    if not reagents:
        return DistillPlan(messages=(error(ErrorCode.NO_REAGENTS),))

    elements = ElementVector()
    for ingredient, qty in picked:
        elements = elements + ingredient.elements * qty

    messages: list[Message] = []
    if reagents > MAX_REAGENTS:
        messages.append(error(ErrorCode.TOO_MANY_REAGENTS, maximum=MAX_REAGENTS, actual=reagents))

    # П-9.5 — особый случай и работает только в одиночку: одна-единственная
    # эссенция тусклой и выше идёт вниз по лестнице, а не вверх, как всё прочее.
    broken_down = False
    yields: tuple[EssenceYield, ...] = ()
    if len(picked) == 1 and reagents == 1:
        ingredient = picked[0][0]
        level, element = essence_level(ingredient), essence_element(ingredient)
        if level is not None and element is not None and level >= MIN_BREAKDOWN_LEVEL:
            yields = break_down(element, level)
            broken_down = True
    if not broken_down:
        yields = distill_elements(elements)
        # Эссенции разных стихий не сливаются (П-9.4), а одинокая фосфорицирующая
        # уже ни на что не делится: экстракт будет потрачен впустую.
        if _as_essences(picked) == {(y.element, y.level): y.count for y in yields}:
            messages.append(error(ErrorCode.DISTILL_NO_CHANGE))

    return DistillPlan(
        elements=elements,
        yields=yields,
        reagents=reagents,
        broken_down=broken_down,
        messages=tuple(messages),
    )
