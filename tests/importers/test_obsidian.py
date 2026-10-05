"""Импорт реальной папки `Алхимия/` (03 §7, §9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from alchimist.core.errors import Severity, WarningCode
from alchimist.core.models import BaseType, IngredientCategory, PotionKind, Rarity
from alchimist.core.rules import check_catalog
from alchimist.importers.obsidian import (
    import_obsidian,
    parse_bases,
    parse_elements,
    parse_habitats,
    parse_rarity,
    split_blocks,
)

SOURCE = Path(__file__).resolve().parents[2] / "Алхимия"
pytestmark = pytest.mark.skipif(not SOURCE.exists(), reason="нет исходных заметок")


@pytest.fixture(scope="module")
def report():
    return import_obsidian(SOURCE)


def messages_of(report, code) -> list:
    return [m for m in report.messages if m.code is code]


# ── §9: импорт даёт 63 реагента и 25 рецептов ────────────────────────────────
def test_counts(report) -> None:
    assert len(report.ingredients) == 63
    assert len(report.potions) == 140
    assert report.known_recipes == 25


def test_all_ids_unique(report) -> None:
    ids = [i.id for i in report.ingredients]
    assert len(ids) == len(set(ids))
    ids = [p.id for p in report.potions]
    assert len(ids) == len(set(ids))


def test_imported_catalog_passes_rules(report) -> None:
    """П-3.2 и П-5.2 выполняются для всех записей, коллизий рецептов нет."""
    assert check_catalog(report.ingredients, report.potions) == []


# ── §7.4: известные проблемы попадают в отчёт ────────────────────────────────
def test_wind_synonym_noted(report) -> None:
    notes = messages_of(report, WarningCode.IMPORT_SYNONYM_APPLIED)
    assert any(m.params["value"] == "Ветер" for m in notes)
    assert all(m.severity is Severity.INFO for m in notes)

    air = next(i for i in report.ingredients if i.name == "Тусклая эссенция воздуха")
    assert air.elements.to_dict() == {"air": 2}


def test_liquid_synonym_noted(report) -> None:
    notes = messages_of(report, WarningCode.IMPORT_SYNONYM_APPLIED)
    assert any(m.params["value"] == "Жидкость" for m in notes)

    lasagna = next(p for p in report.potions if p.name == "Зелье Лазанья")
    assert lasagna.recipe.bases == frozenset({BaseType.LIQUID})


def test_duplicate_cloud_platform_oil(report) -> None:
    duplicates = messages_of(report, WarningCode.IMPORT_DUPLICATE_NAME)
    assert [m.params["name"] for m in duplicates] == ["Масло Облачной Платформы"]

    both = [p for p in report.potions if p.name == "Масло Облачной Платформы"]
    assert {p.id for p in both} == {
        "maslo-oblachnoy-platformy",
        "maslo-oblachnoy-platformy-2",
    }


def test_oil_type_line(report) -> None:
    """«Масло, необычное» → вид oil, редкость 2."""
    for name in ("Масло Излучения", "Стеклянное Масло"):
        potion = next(p for p in report.potions if p.name == name)
        assert potion.kind is PotionKind.OIL
        assert potion.rarity is Rarity.UNCOMMON


def test_sharpening_oil_rarity_note(report) -> None:
    """Пометка «в файле указано как Необычное» не меняет редкость: она редкая."""
    potion = next(p for p in report.potions if p.name == "Масло Заточки")
    assert potion.rarity is Rarity.RARE
    tags = messages_of(report, WarningCode.IMPORT_UNKNOWN_TAG)
    assert any(m.params["name"] == "Масло Заточки" for m in tags)


def test_very_rare_is_epic(report) -> None:
    potion = next(p for p in report.potions if p.name == "Зелье Здоровья Дракона (Очень Редкое)")
    assert potion.rarity is Rarity.EPIC
    assert potion.family == "Зелье Здоровья Дракона"


def test_index_mismatch_reported(report) -> None:
    mismatches = messages_of(report, WarningCode.IMPORT_INDEX_MISMATCH)
    assert any(
        m.params["label"] == "Пушистое мыло" and m.params["target"] == "Пастушье Мыло"
        for m in mismatches
    )


def test_grammar_typo_does_not_break_parsing(report) -> None:
    """«Необычная растение» разбирается по основам слов."""
    ice = next(i for i in report.ingredients if i.name == "Ледяная лоза")
    assert ice.rarity is Rarity.UNCOMMON
    assert ice.category is IngredientCategory.PLANT
    assert ice.is_herb
    assert ice.elements.to_dict() == {"water": 1, "magic": 1}
    assert ice.habitats == ["Арктика", "Холодные пещеры", "Горы"]


def test_jabberwock_keeps_raw_recipe(report) -> None:
    """П-5.9: у Бармаглота нет обычного рецепта, сырой текст — в recipe_note."""
    potion = next(p for p in report.potions if p.name == "Бармаглот")
    assert potion.recipe is None
    assert "3 или больше" in potion.recipe_note
    assert messages_of(report, WarningCode.IMPORT_RECIPE_UNPARSED)


def test_mind_control_variants_block(report) -> None:
    potion = next(p for p in report.potions if p.name == "Зелье Контроля Разума (Редкое)")
    assert potion.recipe is None
    assert "Контроль зверя" in potion.recipe_note
    assert potion.family == "Зелье Контроля Разума"


# ── разбор отдельных записей ─────────────────────────────────────────────────
def test_families(report) -> None:
    """П-5.8: шесть семейств, каждая версия — отдельное зелье."""
    families = {p.family for p in report.potions if p.family}
    assert families == {
        "Зелье Лечения",
        "Зелье Восстановления Маны",
        "Зелье Силы Великана",
        "Зелье Здоровья Дракона",
        "Зелье Сопротивления",
        "Зелье Контроля Разума",
    }


def test_black_market_tag(report) -> None:
    marked = {p.name for p in report.potions if p.is_black_market}
    assert "Любовное Зелье" in marked
    assert "Зелье Лени" in marked


def test_ingredient_categories(report) -> None:
    by_category: dict[IngredientCategory, int] = {}
    for ingredient in report.ingredients:
        by_category[ingredient.category] = by_category.get(ingredient.category, 0) + 1
    assert by_category[IngredientCategory.ESSENCE] == 35
    assert by_category[IngredientCategory.CREATURE] == 4
    assert by_category[IngredientCategory.HERB] + by_category[IngredientCategory.PLANT] == 24
    # Травы и растения — «Травы» для набора травника, эссенции и существа — нет.
    assert sum(1 for i in report.ingredients if i.is_herb) == 24


def test_rarity_equals_units_for_every_ingredient(report) -> None:
    """П-3.2 на реальных данных: все 63 реагента правилу соответствуют."""
    for ingredient in report.ingredients:
        assert ingredient.elements.total == int(ingredient.rarity), ingredient.name


def test_recipe_size_matches_rarity(report) -> None:
    """П-5.2 на реальных данных: все 25 рецептов правилу соответствуют."""
    for potion in report.potions:
        if potion.recipe is not None:
            assert potion.recipe.elements.total == int(potion.rarity) + 1, potion.name


def test_base_distinguishes_real_recipes(report) -> None:
    """П-5.5: одинаковые элементы, разные основы — разные зелья."""
    by_name = {p.name: p for p in report.potions}
    assert by_name["Зелье Силы Огра"].recipe.bases == frozenset({BaseType.LIQUID})
    assert by_name["Динамит"].recipe.bases == frozenset({BaseType.EXPLOSIVE})
    assert by_name["Зелье Силы Огра"].recipe.elements == by_name["Динамит"].recipe.elements

    assert by_name["Зелье Лазанья"].recipe.elements == by_name["Зелье Пищеварения"].recipe.elements
    assert by_name["Зелье Лазанья"].recipe.bases != by_name["Зелье Пищеварения"].recipe.bases


def test_any_base_recipe(report) -> None:
    fire = next(p for p in report.potions if p.name == "Алхимический Огонь")
    assert fire.recipe.is_any_base
    assert fire.recipe.elements.to_dict() == {"fire": 2}


def test_multi_base_recipe(report) -> None:
    healing = next(p for p in report.potions if p.name == "Зелье Лечения (Слабое)")
    assert healing.recipe.bases == frozenset({BaseType.LIQUID, BaseType.VISCOUS})
    assert healing.recipe.elements.to_dict() == {"light": 1, "dark": 1}


def test_essence_placeholder_description_is_empty(report) -> None:
    essence = next(i for i in report.ingredients if i.name == "Тусклая эссенция огня")
    assert essence.description == ""
    assert essence.category is IngredientCategory.ESSENCE
    assert not essence.is_herb


def test_descriptions_do_not_contain_note_lines(report) -> None:
    healing = next(p for p in report.potions if p.name == "Зелье Лечения (Слабое)")
    assert "Примечание" not in healing.description_md
    assert "Рецепт" not in healing.description_md
    assert healing.description_md.startswith("Вы восстанавливаете 2к4+2")


# ── разбор кусочков ──────────────────────────────────────────────────────────
def test_rarity_stems() -> None:
    assert parse_rarity("_Необычная трава_") is Rarity.UNCOMMON
    assert parse_rarity("_Обычная трава_") is Rarity.COMMON
    assert parse_rarity("_Очень Редкое зелье_") is Rarity.EPIC
    assert parse_rarity("_Эпическая эссенция_") is Rarity.EPIC
    assert parse_rarity("_Редкий яд_") is Rarity.RARE
    assert parse_rarity("_Легендарное зелье_") is Rarity.LEGENDARY
    assert parse_rarity("_что-то непонятное_") is None


def test_bases_parsing() -> None:
    assert parse_bases("Любая") == frozenset(BaseType)
    assert parse_bases("Жидкость") == frozenset({BaseType.LIQUID})
    assert parse_bases("Жидкая или Вязкая") == frozenset({BaseType.LIQUID, BaseType.VISCOUS})
    assert parse_bases("взрывная") == frozenset({BaseType.EXPLOSIVE})


def test_habitats_parsing() -> None:
    assert parse_habitats("_Обычная трава, (Лес, Луг, Болота)_") == ["Лес", "Луг", "Болота"]
    assert parse_habitats("_Обычная трава_ (_Луг_)") == ["Луг"]
    assert parse_habitats("_Редкий реагент_") == []


def test_elements_parsing() -> None:
    assert parse_elements("Тьма, Тьма, Огонь").to_dict() == {"fire": 1, "dark": 2}
    assert parse_elements("*Ветер*").to_dict() == {"air": 1}


def test_split_blocks_skips_separators() -> None:
    text = "## A\nодин\n\n---\n## B\nдва\n"
    blocks = list(split_blocks(text, level=2))
    assert [b.title for b in blocks] == ["A", "B"]
    assert "---" not in "".join(blocks[0].lines)
