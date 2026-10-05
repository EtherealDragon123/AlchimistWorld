"""Элементы и мультимножества элементов (П-1.x, 03 §4.1)."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from enum import StrEnum
from typing import Self


class Element(StrEnum):
    """Семь магических стихий (П-1.1)."""

    FIRE = "fire"
    WATER = "water"
    AIR = "air"
    EARTH = "earth"
    LIGHT = "light"
    DARK = "dark"
    MAGIC = "magic"


#: Фиксированный порядок элементов: он же порядок компонентов ElementVector.
ELEMENT_ORDER: tuple[Element, ...] = (
    Element.FIRE,
    Element.WATER,
    Element.AIR,
    Element.EARTH,
    Element.LIGHT,
    Element.DARK,
    Element.MAGIC,
)

ELEMENT_INDEX: dict[Element, int] = {e: i for i, e in enumerate(ELEMENT_ORDER)}

#: Русские названия для отображения (П-1.3).
ELEMENT_NAMES_RU: dict[Element, str] = {
    Element.FIRE: "Огонь",
    Element.WATER: "Вода",
    Element.AIR: "Воздух",
    Element.EARTH: "Земля",
    Element.LIGHT: "Свет",
    Element.DARK: "Тьма",
    Element.MAGIC: "Магия",
}

#: Синонимы для импорта и поиска (П-1.2: «Ветер» = Воздух).
ELEMENT_SYNONYMS_RU: dict[str, Element] = {
    "огонь": Element.FIRE,
    "вода": Element.WATER,
    "воздух": Element.AIR,
    "ветер": Element.AIR,
    "земля": Element.EARTH,
    "свет": Element.LIGHT,
    "тьма": Element.DARK,
    "магия": Element.MAGIC,
}


def _normalize(text: str) -> str:
    return text.strip().strip("*_ .·").casefold().replace("ё", "е")


def parse_element(text: str) -> Element | None:
    """Разбирает название элемента с учётом синонимов. None, если не узнали."""
    key = _normalize(text)
    if not key:
        return None
    for name, element in ELEMENT_SYNONYMS_RU.items():
        if _normalize(name) == key:
            return element
    try:
        return Element(key)
    except ValueError:
        return None


class ElementVector:
    """Мультимножество элементов: 7 неотрицательных целых в фиксированном порядке.

    Неизменяемый и хешируемый, поэтому годится ключом словаря: на этом держатся
    индекс рецептов (03 §5.5) и поиск по журналу (П-7.6).

    Вычитание может дать отрицательные компоненты — так считается недостача
    в «Почти готово» (FR-6.1).
    """

    __slots__ = ("counts",)

    counts: tuple[int, int, int, int, int, int, int]

    def __init__(self, counts: Iterable[int] = (0, 0, 0, 0, 0, 0, 0)) -> None:
        values = tuple(int(c) for c in counts)
        if len(values) != len(ELEMENT_ORDER):
            raise ValueError(f"ожидалось {len(ELEMENT_ORDER)} компонент, получено {len(values)}")
        object.__setattr__(self, "counts", values)

    # ── создание ──────────────────────────────────────────────────────────
    @classmethod
    def _make(cls, counts: tuple[int, ...]) -> ElementVector:
        """Быстрый конструктор без проверок: только для внутренних горячих путей."""
        vector = object.__new__(cls)
        object.__setattr__(vector, "counts", counts)
        return vector

    @classmethod
    def from_dict(cls, data: Mapping[str, int] | None) -> Self:
        """Из словаря вида {"fire": 2}. Неизвестные ключи — ошибка."""
        counts = [0] * len(ELEMENT_ORDER)
        for key, value in (data or {}).items():
            element = parse_element(key)
            if element is None:
                raise ValueError(f"неизвестный элемент: {key!r}")
            counts[ELEMENT_INDEX[element]] += int(value)
        return cls(counts)

    @classmethod
    def from_elements(cls, elements: Iterable[Element]) -> Self:
        """Из последовательности элементов с повторами: [FIRE, FIRE] → {fire: 2}."""
        counts = [0] * len(ELEMENT_ORDER)
        for element in elements:
            counts[ELEMENT_INDEX[element]] += 1
        return cls(counts)

    # ── чтение ────────────────────────────────────────────────────────────
    def to_dict(self) -> dict[str, int]:
        """Словарь без нулей, в фиксированном порядке: {"fire": 2}."""
        return {
            str(element.value): self.counts[i]
            for i, element in enumerate(ELEMENT_ORDER)
            if self.counts[i]
        }

    def __getitem__(self, element: Element) -> int:
        return self.counts[ELEMENT_INDEX[element]]

    def get(self, element: Element) -> int:
        return self.counts[ELEMENT_INDEX[element]]

    @property
    def total(self) -> int:
        """Сумма единиц."""
        return sum(self.counts)

    def items(self) -> Iterator[tuple[Element, int]]:
        """Пары (элемент, количество) для ненулевых компонент."""
        for i, element in enumerate(ELEMENT_ORDER):
            if self.counts[i]:
                yield element, self.counts[i]

    # ── арифметика ────────────────────────────────────────────────────────
    def __add__(self, other: ElementVector) -> ElementVector:
        return ElementVector._make(
            tuple(a + b for a, b in zip(self.counts, other.counts, strict=True))
        )

    def __sub__(self, other: ElementVector) -> ElementVector:
        """Покомпонентная разность. Может дать отрицательные значения."""
        return ElementVector._make(
            tuple(a - b for a, b in zip(self.counts, other.counts, strict=True))
        )

    def __mul__(self, factor: int) -> ElementVector:
        return ElementVector._make(tuple(c * factor for c in self.counts))

    __rmul__ = __mul__

    def fits_in(self, other: ElementVector) -> bool:
        """Покомпонентно ≤ other."""
        return all(a <= b for a, b in zip(self.counts, other.counts, strict=True))

    def clamped(self) -> ElementVector:
        """Отрицательные компоненты обнуляются: недостача как отдельный вектор."""
        return ElementVector._make(tuple(c if c > 0 else 0 for c in self.counts))

    def max_repeats_in(self, other: ElementVector) -> int:
        """Сколько раз self целиком помещается в other. Для пустого self — 0."""
        if self.is_empty:
            return 0
        return min(b // a for a, b in zip(self.counts, other.counts, strict=True) if a)

    @property
    def is_empty(self) -> bool:
        return not any(self.counts)

    @property
    def is_negative(self) -> bool:
        return any(c < 0 for c in self.counts)

    # ── служебное ─────────────────────────────────────────────────────────
    def __bool__(self) -> bool:
        return any(self.counts)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ElementVector):
            return self.counts == other.counts
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.counts)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("ElementVector неизменяем")

    # Вектор неизменяем, поэтому копия — он сам.
    def __copy__(self) -> ElementVector:
        return self

    def __deepcopy__(self, memo: dict) -> ElementVector:
        return self

    def __reduce__(self) -> tuple:
        return (ElementVector, (self.counts,))

    def __repr__(self) -> str:
        inner = ", ".join(f"{e.value}={c}" for e, c in self.items())
        return f"ElementVector({inner})"

    def format_ru(self, *, separator: str = ", ") -> str:
        """«Огонь×2, Свет×1» — для подсказок и отчётов."""
        if self.is_empty:
            return "—"
        return separator.join(f"{ELEMENT_NAMES_RU[e]}×{c}" for e, c in self.items())
