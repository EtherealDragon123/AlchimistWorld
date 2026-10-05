from __future__ import annotations

import pytest

from alchimist.core.elements import ELEMENT_ORDER, Element, ElementVector, parse_element


def test_wind_is_air() -> None:
    """П-1.2: «Ветер» — синоним Воздуха."""
    assert parse_element("Ветер") is Element.AIR
    assert parse_element("Воздух") is Element.AIR
    assert parse_element("_Ветер_") is Element.AIR
    assert parse_element("щавель") is None


def test_from_elements_counts_repeats() -> None:
    v = ElementVector.from_elements([Element.DARK, Element.DARK, Element.FIRE])
    assert v.to_dict() == {"fire": 1, "dark": 2}
    assert v.total == 3


def test_arithmetic_and_fits_in() -> None:
    a = ElementVector.from_dict({"fire": 2})
    b = ElementVector.from_dict({"fire": 1, "light": 1})
    assert (a + b).to_dict() == {"fire": 3, "light": 1}
    assert (a - b).counts[ELEMENT_ORDER.index(Element.LIGHT)] == -1
    assert (a - b).is_negative
    assert b.fits_in(a) is False
    assert ElementVector.from_dict({"fire": 1}).fits_in(a) is True


def test_hashable_as_dict_key() -> None:
    key = ElementVector.from_dict({"dark": 1, "light": 1})
    same = ElementVector.from_elements([Element.LIGHT, Element.DARK])
    assert {key: "x"}[same] == "x"


def test_immutable() -> None:
    v = ElementVector.from_dict({"fire": 1})
    with pytest.raises(AttributeError):
        v.counts = (0,) * 7  # type: ignore[misc]


def test_format_ru() -> None:
    assert ElementVector.from_dict({"fire": 2, "light": 1}).format_ru() == "Огонь×2, Свет×1"
    assert ElementVector().format_ru() == "—"


def test_unknown_element_rejected() -> None:
    with pytest.raises(ValueError, match="неизвестный элемент"):
        ElementVector.from_dict({"plasma": 1})
