from __future__ import annotations

from alchimist.core.ids import normalize_name, slugify, unique_id


def test_slug_matches_documented_examples() -> None:
    """03 §6.9 и примеры из 03 §6.3–6.4."""
    assert slugify("Могильная Лоза") == "mogilnaya-loza"
    assert slugify("Семя ночного пламени") == "semya-nochnogo-plameni"
    assert slugify("Зелье Лечения (Слабое)") == "zele-lecheniya-slaboe"
    assert slugify("Бармаглот") == "barmaglot"


def test_suffix_on_collision() -> None:
    taken = {"maslo-oblachnoy-platformy"}
    assert unique_id("Масло Облачной Платформы", taken) == "maslo-oblachnoy-platformy-2"
    taken.add("maslo-oblachnoy-platformy-2")
    assert unique_id("Масло Облачной Платформы", taken) == "maslo-oblachnoy-platformy-3"


def test_normalize_name_ignores_case_and_yo() -> None:
    assert normalize_name("Щёлкорех") == normalize_name("щелкорех")
    assert normalize_name("  Зелье   Лечения ") == "зелье лечения"
