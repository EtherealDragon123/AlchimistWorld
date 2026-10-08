"""Фильтры списков (FR-1.1, FR-2.1, FR-8.2).

Qt возвращает из виджетов `StrEnum` обычной строкой, поэтому сравнения через `is`
здесь молча переставали работать. Тесты держат каждый фильтр под присмотром.
"""

from __future__ import annotations

import pytest

from alchimist.core.models import (
    BaseType,
    IngredientCategory,
    JournalEntryType,
    Outcome,
    PotionKind,
    Rarity,
    ResultKind,
)
from alchimist.services.brewing import BrewRequest
from alchimist.ui_qt.pages.catalog import CatalogPage
from alchimist.ui_qt.pages.journal import JournalPage


def _select(combo, value) -> None:
    index = combo.findData(value)
    assert index >= 0, f"в списке нет варианта {value!r}"
    combo.setCurrentIndex(index)


def _names(tree) -> set[str]:
    return {tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())}


@pytest.fixture
def catalog_page(window):
    page = next(p for p in window.pages if isinstance(p, CatalogPage))
    window.go_to(CatalogPage)
    return page


# ── реагенты (FR-1.1) ────────────────────────────────────────────────────────
def test_ingredient_category_filter(catalog_page) -> None:
    tab = catalog_page.ingredients
    everything = _names(tab.tree)
    assert "Щёлкорех" in everything and "Тусклая эссенция огня" in everything

    _select(tab.filters._widgets["category"], IngredientCategory.ESSENCE)
    assert _names(tab.tree) == {
        "Тусклая эссенция огня",
        "Фосфорицирующая эссенция света",
    }

    _select(tab.filters._widgets["category"], IngredientCategory.CREATURE)
    assert _names(tab.tree) == {"Кровь дракочерепахи"}

    # Отдельной «Травы» больше нет: все травы — растения (П-3.3).
    _select(tab.filters._widgets["category"], IngredientCategory.PLANT)
    plants = _names(tab.tree)
    assert {"Ледяная лоза", "Сок Стального Дерева", "Щёлкорех", "Фанана"} <= plants
    assert "Тусклая эссенция огня" not in plants and "Кровь дракочерепахи" not in plants


def test_ingredient_rarity_filter(catalog_page) -> None:
    tab = catalog_page.ingredients
    _select(tab.filters._widgets["rarity"], Rarity.RARE)
    assert _names(tab.tree) == {"Семя ночного пламени", "Кровь дракочерепахи"}


def test_ingredient_element_filter(catalog_page) -> None:
    tab = catalog_page.ingredients
    from alchimist.core.elements import Element

    _select(tab.filters._widgets["element"], Element.MAGIC)
    assert _names(tab.tree) == {"Ледяная лоза"}
    assert "herb" not in tab.filters._widgets  # фильтра «Только травы» больше нет


def test_ingredient_filters_combine(catalog_page) -> None:
    tab = catalog_page.ingredients
    _select(tab.filters._widgets["category"], IngredientCategory.PLANT)
    _select(tab.filters._widgets["rarity"], Rarity.COMMON)
    assert "Семя ночного пламени" not in _names(tab.tree)  # растение, но редкое
    assert "Щёлкорех" in _names(tab.tree)


# ── зелья (FR-2.1) ───────────────────────────────────────────────────────────
def test_potion_kind_filter(catalog_page) -> None:
    tab = catalog_page.potions
    _select(tab.filters._widgets["kind"], PotionKind.POISON)
    assert _names(tab.tree) == {
        "Зелье Безобразной Плоти",
        "Обычный Яд",
    }

    _select(tab.filters._widgets["kind"], PotionKind.POTION)
    names = _names(tab.tree)
    assert "Алхимический Огонь" in names
    assert "Обычный Яд" not in names


def test_potion_rarity_and_recipe_filters(catalog_page) -> None:
    tab = catalog_page.potions
    _select(tab.filters._widgets["rarity"], Rarity.UNCOMMON)
    assert _names(tab.tree) == {"Пламя Саламандры", "Бармаглот"}

    tab.filters._widgets["rarity"].setCurrentIndex(0)
    _select(tab.filters._widgets["recipe"], False)
    assert _names(tab.tree) == {"Бармаглот"}


def test_potion_family_filter(catalog_page) -> None:
    tab = catalog_page.potions
    _select(tab.filters._widgets["family"], "Зелье Лечения")
    assert _names(tab.tree) == {"Зелье Лечения (Слабое)"}


# ── журнал (FR-8.2) ──────────────────────────────────────────────────────────
@pytest.fixture
def journal_page(window, ui_app):
    ui_app.inventory.set_reagent("shcholkorekh", 2)
    ui_app.inventory.set_reagent("tkanevyy-list", 2)
    ui_app.brewing.brew(
        BrewRequest(
            base=BaseType.LIQUID,
            reagents={"tkanevyy-list": 2},
            result_kind=ResultKind.KNOWN,
            potion_id="zele-lazanya",
        )
    )
    ui_app.brewing.brew(
        BrewRequest(
            base=BaseType.EXPLOSIVE,
            reagents={"shcholkorekh": 2},
            outcome=Outcome.FAILURE,
            result_kind=ResultKind.NONE,
        )
    )
    page = next(p for p in window.pages if isinstance(p, JournalPage))
    window.go_to(JournalPage)
    return page


def test_journal_base_filter(journal_page) -> None:
    assert journal_page.tree.topLevelItemCount() == 2

    _select(journal_page.filters._widgets["base"], BaseType.EXPLOSIVE)
    assert journal_page.tree.topLevelItemCount() == 1
    assert journal_page.tree.topLevelItem(0).text(2) == "Взрывная"

    _select(journal_page.filters._widgets["base"], BaseType.LIQUID)
    assert journal_page.tree.topLevelItemCount() == 1
    assert journal_page.tree.topLevelItem(0).text(2) == "Жидкая"


def test_journal_type_and_outcome_filters(journal_page, ui_app) -> None:
    ui_app.brewing.use_potion("zele-lazanya")
    assert journal_page.tree.topLevelItemCount() == 3

    _select(journal_page.filters._widgets["type"], JournalEntryType.USE)
    assert journal_page.tree.topLevelItemCount() == 1

    journal_page.filters._widgets["type"].setCurrentIndex(0)
    _select(journal_page.filters._widgets["outcome"], Outcome.FAILURE)
    assert journal_page.tree.topLevelItemCount() == 1


def test_journal_potion_filter(journal_page) -> None:
    _select(journal_page.filters._widgets["potion"], "zele-lazanya")
    assert journal_page.tree.topLevelItemCount() == 1


# ── «Могу сварить»: те же фильтры, что в справочнике, плюс порядок ───────────
@pytest.fixture
def brew_page(window, ui_app):
    from alchimist.ui_qt.pages.can_brew import CanBrewPage

    ui_app.inventory.set_reagent("shcholkorekh", 2)  # Огонь×1
    ui_app.inventory.set_reagent("tkanevyy-list", 2)  # Земля×1
    ui_app.inventory.set_reagent("podlunnukh", 2)  # Тьма×1
    ui_app.inventory.set_reagent("svechnaya-roza", 1)  # Свет×1
    page = next(p for p in window.pages if isinstance(p, CanBrewPage))
    window.go_to(CanBrewPage)
    page.max_excess.setValue(0)
    return page


def test_can_brew_rarity_filter(brew_page) -> None:
    assert {"Алхимический Огонь", "Пламя Саламандры"} <= _names(brew_page.tree)

    _select(brew_page.filters._widgets["rarity"], Rarity.UNCOMMON)
    assert _names(brew_page.tree) == {"Пламя Саламандры"}

    _select(brew_page.filters._widgets["rarity"], Rarity.COMMON)
    assert "Пламя Саламандры" not in _names(brew_page.tree)


def test_can_brew_kind_filter(brew_page) -> None:
    _select(brew_page.filters._widgets["kind"], PotionKind.POISON)
    assert _names(brew_page.tree) <= {"Зелье Безобразной Плоти", "Обычный Яд"}
    assert _names(brew_page.tree)

    _select(brew_page.filters._widgets["kind"], PotionKind.POTION)
    assert "Зелье Безобразной Плоти" not in _names(brew_page.tree)


def test_can_brew_family_filter(brew_page) -> None:
    _select(brew_page.filters._widgets["family"], "Зелье Лечения")
    assert _names(brew_page.tree) == {"Зелье Лечения (Слабое)"}


def test_can_brew_sort_order(brew_page) -> None:
    def order() -> list[str]:
        return [
            brew_page.tree.topLevelItem(i).text(0)
            for i in range(brew_page.tree.topLevelItemCount())
        ]

    _select(brew_page.sort_by, "name")
    assert order() == sorted(order(), key=str.casefold)

    _select(brew_page.sort_by, "difficulty")
    levels = [
        int(brew_page.tree.topLevelItem(i).text(3))
        for i in range(brew_page.tree.topLevelItemCount())
    ]
    assert levels == sorted(levels)

    _select(brew_page.sort_by, "rarity")
    # По редкости: обычные идут раньше необычных.
    assert order().index("Алхимический Огонь") < order().index("Пламя Саламандры")


def test_can_brew_filters_combine_with_search(brew_page) -> None:
    _select(brew_page.filters._widgets["rarity"], Rarity.COMMON)
    brew_page.search.setText("огонь")
    brew_page.refresh()
    assert _names(brew_page.tree) == {"Алхимический Огонь"}
