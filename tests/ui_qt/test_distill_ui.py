"""Дистилляция в «Лаборатории»: переключение режима и разбор (FR-13.x, П-9)."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QMessageBox

from alchimist.core.distill import MAX_REAGENTS, essence_name_ru
from alchimist.core.elements import ELEMENT_ORDER, Element
from alchimist.core.elements import ElementVector as EV
from alchimist.core.models import (
    ALL_BASES,
    Catalog,
    Ingredient,
    IngredientCategory,
    Potion,
    Rarity,
    Recipe,
)
from alchimist.services.distilling import EXTRACT_ID
from alchimist.ui_qt.pages.lab import BREW, DISTILL, LabPage

LEVELS = (1, 2, 3, 4, 5)


def essence_id(element: Element, level: int) -> str:
    return f"essence-{element.value}-{level}"


@pytest.fixture
def catalog(ingredients, potions) -> Catalog:
    """Справочник фикстуры плюс вся лестница эссенций и сам экстракт."""
    ladder = [
        Ingredient(
            id=essence_id(element, level),
            name=essence_name_ru(element, level),
            rarity=Rarity(level),
            category=IngredientCategory.ESSENCE,
            elements=EV.from_dict({element.value: level}),
        )
        for element in ELEMENT_ORDER
        for level in LEVELS
    ]
    keep = [i for i in ingredients.values() if i.category is not IngredientCategory.ESSENCE]
    extract = Potion(
        id=EXTRACT_ID,
        name="Дистиллирующий Экстракт",
        rarity=Rarity.UNCOMMON,
        recipe=Recipe(ALL_BASES, EV.from_dict({"fire": 1, "water": 1, "dark": 1})),
    )
    return Catalog([*keep, *ladder], [*potions.values(), extract])


def lab(window) -> LabPage:
    window.go_to(LabPage)
    return next(p for p in window.pages if isinstance(p, LabPage))


@pytest.fixture(autouse=True)
def flask(ui_app):
    """Флакон экстракта — обязательное условие разбора (П-9.6), он нужен всем тестам."""
    ui_app.inventory.set_potion(EXTRACT_ID, 2)
    return ui_app


def rows(tree) -> list[tuple[str, str]]:
    return [
        (tree.topLevelItem(i).text(0), tree.topLevelItem(i).text(1))
        for i in range(tree.topLevelItemCount())
    ]


def set_mode(page: LabPage, mode: str) -> None:
    page.mode.setCurrentIndex(page.mode.findData(mode))


def test_mode_switch_swaps_the_right_panel(window) -> None:
    page = lab(window)
    assert not page.distilling
    assert page.base.isVisible()

    set_mode(page, DISTILL)
    assert page.distilling
    assert not page.base.isVisible()
    assert not page.base_label.isVisible()
    assert page.panels.currentIndex() == 1
    assert "экстракт" in page.add_button.text()

    set_mode(page, BREW)
    assert page.panels.currentIndex() == 0
    assert page.base.isVisible()


def test_seven_earth_gives_two_essences(window, ui_app) -> None:
    """Пример мастера прямо на экране: 7 земли → сияющая и тусклая."""
    ui_app.inventory.set_reagent("sok-stalnogo-dereva", 3)  # Земля×2
    ui_app.inventory.set_reagent("tkanevyy-list", 1)  # Земля×1
    page = lab(window)
    set_mode(page, DISTILL)
    page.cauldron = {"sok-stalnogo-dereva": 3, "tkanevyy-list": 1}
    page.refresh()

    assert rows(page.essences) == [
        ("Сияющая эссенция земли", "×1"),
        ("Тусклая эссенция земли", "×1"),
    ]
    assert page.elements.vector() == EV.from_dict({"earth": 7})
    assert page.distill_button.isEnabled()


def test_pot_label_counts_reagents(window, ui_app) -> None:
    ui_app.inventory.set_reagent("tkanevyy-list", 9)
    page = lab(window)
    set_mode(page, DISTILL)
    page.cauldron = {"tkanevyy-list": 2}
    page.refresh()
    assert page.pot_label.text() == f"Дистиллирующий экстракт — 2 из {MAX_REAGENTS}"

    set_mode(page, BREW)
    assert page.pot_label.text() == "Котёл"


def test_extract_holds_only_five(window, ui_app) -> None:
    """П-9.1: шестой реагент в экстракт уже не кладётся."""
    ui_app.inventory.set_reagent("tkanevyy-list", 9)
    page = lab(window)
    set_mode(page, DISTILL)
    for _ in range(MAX_REAGENTS + 3):
        # Список перестраивается после каждого добавления, строку надо брать заново.
        page._add(page.stock.topLevelItem(0))
    assert page.cauldron == {"tkanevyy-list": MAX_REAGENTS}

    # В котле того же ограничения нет.
    set_mode(page, BREW)
    page._add(page.stock.topLevelItem(0))
    assert page.cauldron["tkanevyy-list"] == MAX_REAGENTS + 1


def test_missing_flask_disables_the_button(window, ui_app) -> None:
    """П-9.6: реагенты есть, эссенции посчитаны, а разобрать не в чем."""
    ui_app.inventory.set_potion(EXTRACT_ID, 0)
    ui_app.inventory.set_reagent("sok-stalnogo-dereva", 1)
    page = lab(window)
    set_mode(page, DISTILL)
    page.cauldron = {"sok-stalnogo-dereva": 1}
    page.refresh()
    assert rows(page.essences) == [("Тусклая эссенция земли", "×1")]
    assert not page.distill_button.isEnabled()


def test_pointless_distillation_disables_the_button(window, ui_app) -> None:
    ui_app.inventory.set_reagent(essence_id(Element.FIRE, 1), 1)
    page = lab(window)
    set_mode(page, DISTILL)
    page.cauldron = {essence_id(Element.FIRE, 1): 1}
    page.refresh()
    assert not page.distill_button.isEnabled()


def test_lone_essence_breaks_down(window, ui_app) -> None:
    """П-9.5: одинокая сияющая рассыпается на пять фосфорицирующих."""
    ui_app.inventory.set_reagent(essence_id(Element.FIRE, 5), 1)
    page = lab(window)
    set_mode(page, DISTILL)
    page.cauldron = {essence_id(Element.FIRE, 5): 1}
    page.refresh()
    assert rows(page.essences) == [("Фосфорицирующая эссенция огня", "×5")]


def test_distilling_moves_things_in_the_bag(window, ui_app, monkeypatch) -> None:
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    ui_app.inventory.set_reagent("sok-stalnogo-dereva", 1)  # Земля×2
    page = lab(window)
    set_mode(page, DISTILL)
    page.cauldron = {"sok-stalnogo-dereva": 1}
    page.refresh()
    page._distill()

    assert page.cauldron == {}
    assert ui_app.inventory.reagent_qty("sok-stalnogo-dereva") == 0
    assert ui_app.inventory.reagent_qty(essence_id(Element.EARTH, 2)) == 1
    assert ui_app.inventory.potion_qty(EXTRACT_ID) == 1


def test_queue_reserves_apply_to_distillation_too(window, ui_app) -> None:
    """Отложенное в очередь в экстракт не попадает — как и в котёл (FR-12.6)."""
    ui_app.inventory.set_reagent("shcholkorekh", 2)
    ui_app.queue.add("alkhimicheskiy-ogon", next(iter(ALL_BASES)), {"shcholkorekh": 2})
    page = lab(window)
    set_mode(page, DISTILL)
    assert rows(page.stock) == []
