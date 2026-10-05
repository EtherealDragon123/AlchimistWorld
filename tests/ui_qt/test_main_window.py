"""Интерфейс собирается и показывает то, что вернули сервисы."""

from __future__ import annotations

from PySide6.QtCore import Qt

from alchimist.core.models import BaseType, Kit, Outcome, ResultKind
from alchimist.services.brewing import BrewRequest
from alchimist.ui_qt.pages.almost import AlmostPage
from alchimist.ui_qt.pages.can_brew import CanBrewPage
from alchimist.ui_qt.pages.catalog import CatalogPage
from alchimist.ui_qt.pages.journal import JournalPage
from alchimist.ui_qt.pages.lab import LabPage
from alchimist.ui_qt.pages.potions import MyPotionsPage
from alchimist.ui_qt.pages.reagents import ReagentsPage
from alchimist.ui_qt.pages.settings import SettingsPage


def _visit_all(window) -> list[str]:
    seen = []
    for row in range(window.nav.count()):
        item = window.nav.item(row)
        if item.data(Qt.ItemDataRole.UserRole) is None:
            continue
        window.nav.setCurrentRow(row)
        seen.append(type(window.stack.currentWidget()).__name__)
    return seen


def test_every_page_opens(window) -> None:
    assert _visit_all(window) == [
        "CanBrewPage",
        "AlmostPage",
        "LabPage",
        "ReagentsPage",
        "MyPotionsPage",
        "CatalogPage",
        "JournalPage",
        "SettingsPage",
    ]


def test_can_brew_reflects_inventory(window, ui_app) -> None:
    page = next(p for p in window.pages if isinstance(p, CanBrewPage))
    window.go_to(CanBrewPage)
    assert page.tree.topLevelItemCount() == 0
    assert page.empty.isVisible()

    ui_app.inventory.set_reagent("shcholkorekh", 2)
    page.activate()
    assert page.tree.topLevelItemCount() == 1
    top = page.tree.topLevelItem(0)
    assert top.text(0) == "Алхимический Огонь"
    # Любая основа — одна строка, а не три (П-5.1).
    assert top.childCount() == 1
    assert top.child(0).text(1).startswith("Любая")


def test_search_filters_can_brew(window, ui_app) -> None:
    ui_app.inventory.set_reagent("shcholkorekh", 1)
    ui_app.inventory.set_reagent("tkanevyy-list", 1)
    page = next(p for p in window.pages if isinstance(p, CanBrewPage))
    window.go_to(CanBrewPage)
    assert page.tree.topLevelItemCount() >= 2

    page.search.setText("динамит")
    page.refresh()
    assert page.tree.topLevelItemCount() == 1
    assert page.tree.topLevelItem(0).text(0) == "Динамит"


def test_almost_page_shows_missing(window, ui_app) -> None:
    ui_app.inventory.set_reagent("shcholkorekh", 2)
    page = next(p for p in window.pages if isinstance(p, AlmostPage))
    window.go_to(AlmostPage)
    rows = {
        page.tree.topLevelItem(i).text(0): page.tree.topLevelItem(i)
        for i in range(page.tree.topLevelItemCount())
    }
    assert "Пламя Саламандры" in rows
    assert rows["Пламя Саламандры"].text(1) == "Свет×1"
    assert rows["Пламя Саламандры"].childCount() >= 1


def test_lab_updates_sum_and_hint(window, ui_app) -> None:
    ui_app.inventory.set_reagent("tkanevyy-list", 2)
    page = next(p for p in window.pages if isinstance(p, LabPage))
    window.go_to(LabPage)

    assert page.stock.topLevelItemCount() == 1
    page._add(page.stock.topLevelItem(0))
    page._add(page.stock.topLevelItem(0))
    assert page.cauldron == {"tkanevyy-list": 2}
    assert page.elements.vector().to_dict() == {"earth": 2}
    assert "Зелье Лазанья" in page.hint._label.text()

    page._remove(page.pot.topLevelItem(0))
    assert page.cauldron == {"tkanevyy-list": 1}


def test_lab_warns_when_kit_forbids(window, ui_app) -> None:
    ui_app.settings.set_kits((Kit.HERBALIST,))
    ui_app.inventory.set_reagent("tusklaya-essentsiya-ognya", 1)
    page = next(p for p in window.pages if isinstance(p, LabPage))
    window.go_to(LabPage)
    page._add(page.stock.topLevelItem(0))
    assert "не разрешают" in page.hint._label.text()


def test_reagents_page_steppers(window, ui_app) -> None:
    ui_app.inventory.set_reagent("fanana", 1)
    page = next(p for p in window.pages if isinstance(p, ReagentsPage))
    window.go_to(ReagentsPage)
    page.tree.setCurrentItem(page.tree.topLevelItem(0))

    page._step(1)
    assert ui_app.inventory.reagent_qty("fanana") == 2
    page.tree.setCurrentItem(page.tree.topLevelItem(0))
    page._step(-2)
    assert ui_app.inventory.reagent_qty("fanana") == 0
    assert page.tree.topLevelItemCount() == 0


def test_potions_page_use(window, ui_app) -> None:
    ui_app.inventory.set_potion("zele-lecheniya-slaboe", 2)
    page = next(p for p in window.pages if isinstance(p, MyPotionsPage))
    window.go_to(MyPotionsPage)
    page.tree.setCurrentItem(page.tree.topLevelItem(0))
    page._use()
    assert ui_app.inventory.potion_qty("zele-lecheniya-slaboe") == 1
    assert ui_app.journal.entries()[0].type.value == "use"


def test_catalog_page_lists_and_filters(window, ui_app) -> None:
    page = next(p for p in window.pages if isinstance(p, CatalogPage))
    window.go_to(CatalogPage)
    assert page.ingredients.tree.topLevelItemCount() == len(ui_app.catalog.ingredients())
    assert page.potions.tree.topLevelItemCount() == len(ui_app.catalog.potions())

    page.potions.filters._widgets["recipe"].setCurrentIndex(2)  # «неизвестен»
    page.potions.refresh()
    names = {
        page.potions.tree.topLevelItem(i).text(0)
        for i in range(page.potions.tree.topLevelItemCount())
    }
    assert names == {"Бармаглот"}


def test_catalog_marks_warnings(window, ui_app) -> None:
    from alchimist.core.elements import ElementVector as EV
    from alchimist.core.models import Potion, Recipe

    ui_app.add_potion(
        Potion(
            id="",
            name="Двойник Лазаньи",
            recipe=Recipe(frozenset({BaseType.LIQUID}), EV.from_dict({"earth": 2})),
        )
    )
    page = next(p for p in window.pages if isinstance(p, CatalogPage))
    window.go_to(CatalogPage)
    marked = [
        page.potions.tree.topLevelItem(i).text(0)
        for i in range(page.potions.tree.topLevelItemCount())
        if page.potions.tree.topLevelItem(i).text(0).endswith("⚠")
    ]
    assert "Двойник Лазаньи ⚠" in marked
    assert "Зелье Лазанья ⚠" in marked


def test_journal_page_shows_brew(window, ui_app) -> None:
    ui_app.inventory.set_reagent("shcholkorekh", 2)
    ui_app.brewing.brew(
        BrewRequest(
            base=BaseType.LIQUID,
            reagents={"shcholkorekh": 2},
            outcome=Outcome.SUCCESS,
            result_kind=ResultKind.KNOWN,
            potion_id="alkhimicheskiy-ogon",
            note="проверка",
        )
    )
    page = next(p for p in window.pages if isinstance(p, JournalPage))
    window.go_to(JournalPage)
    assert page.tree.topLevelItemCount() == 1
    item = page.tree.topLevelItem(0)
    assert item.text(1) == "варка"
    assert item.text(2) == "Жидкая"
    assert "Щёлкорех×2" in item.text(3)
    assert item.text(4) == "Огонь×2"
    assert item.text(5) == "10"  # обычное зелье, одна порция, без лишнего (П-8)
    assert "Алхимический Огонь" in item.text(6)


def test_settings_page_kits_roundtrip(window, ui_app) -> None:
    page = next(p for p in window.pages if isinstance(p, SettingsPage))
    window.go_to(SettingsPage)
    page.kit_checks[Kit.HERBALIST].setChecked(True)
    page.kit_checks[Kit.ALCHEMIST].setChecked(False)
    assert ui_app.settings.kits == (Kit.HERBALIST,)

    ui_app.reload()
    assert ui_app.settings.settings.kits == (Kit.HERBALIST,)


def test_window_title_follows_character_name(window, ui_app) -> None:
    ui_app.settings.set_character_name("Гримли")
    assert window.windowTitle() == "AlchimistWorld — Гримли"


def test_status_bar_counts(window, ui_app) -> None:
    ui_app.inventory.set_reagent("fanana", 3)
    ui_app.inventory.set_potion("zele-lecheniya-slaboe", 1)
    message = window.statusBar().currentMessage()
    assert "реагентов: 3" in message
    assert "зелий: 1" in message


def test_journal_combination_search(window, ui_app) -> None:
    """FR-8.4: «пробовал ли я Огонь+Огонь на жидкой основе?»"""
    from alchimist.core.elements import ElementVector as EV

    ui_app.inventory.set_reagent("shcholkorekh", 2)
    ui_app.inventory.set_reagent("tkanevyy-list", 2)
    ui_app.brewing.brew(
        BrewRequest(
            base=BaseType.LIQUID,
            reagents={"shcholkorekh": 2},
            result_kind=ResultKind.KNOWN,
            potion_id="alkhimicheskiy-ogon",
        )
    )
    ui_app.brewing.brew(
        BrewRequest(
            base=BaseType.LIQUID,
            reagents={"tkanevyy-list": 2},
            result_kind=ResultKind.KNOWN,
            potion_id="zele-lazanya",
        )
    )
    page = next(p for p in window.pages if isinstance(p, JournalPage))
    window.go_to(JournalPage)
    assert page.tree.topLevelItemCount() == 2

    page.by_combination.setChecked(True)
    page.combination.set_vector(EV.from_dict({"fire": 2}))
    assert page.tree.topLevelItemCount() == 1
    assert "Алхимический Огонь" in page.tree.topLevelItem(0).text(6)


def test_theme_selector_applies_and_remembers(window, ui_app, tmp_path) -> None:
    """FR-9.5: выбор темы применяется сразу и переживает перезапуск."""
    from alchimist.core.models import Theme
    from alchimist.services import build_app
    from alchimist.ui_qt.pages.settings import SettingsPage
    from alchimist.ui_qt.theme import current_theme

    page = next(p for p in window.pages if isinstance(p, SettingsPage))
    window.go_to(SettingsPage)
    assert current_theme() is Theme.DARK
    assert page.theme.currentData() == Theme.DARK

    page.theme.setCurrentIndex(page.theme.findData(Theme.LIGHT))
    assert ui_app.settings.theme is Theme.LIGHT
    assert current_theme() is Theme.LIGHT
    assert build_app(tmp_path).settings.theme is Theme.LIGHT

    page.theme.setCurrentIndex(page.theme.findData(Theme.DARK))
    assert current_theme() is Theme.DARK


def test_theme_switch_repaints_pages(window, ui_app) -> None:
    from alchimist.core.models import Theme
    from alchimist.ui_qt.theme import rarity_color

    ui_app.inventory.set_reagent("semya-nochnogo-plameni", 1)
    page = next(p for p in window.pages if isinstance(p, ReagentsPage))
    window.go_to(ReagentsPage)
    dark = page.tree.topLevelItem(0).foreground(1).color().name()

    ui_app.settings.set_theme(Theme.LIGHT)
    light = page.tree.topLevelItem(0).foreground(1).color().name()
    assert dark != light
    assert light == rarity_color(ui_app.catalog.ingredient("semya-nochnogo-plameni").rarity).name()


def test_reagents_summary_matches_real_totals(window, ui_app) -> None:
    """FR-3.5: 999 Крови дракочерепахи — это 999 Огня и 1998 Воды, а не «20 и 20»."""
    ui_app.inventory.set_reagent("krov-drakocherepakhi", 999)  # Вода×2, Огонь×1
    ui_app.inventory.set_reagent("shcholkorekh", 3)  # Огонь×1

    page = next(p for p in window.pages if isinstance(p, ReagentsPage))
    window.go_to(ReagentsPage)

    expected = ui_app.inventory.element_summary(ui_app.catalog.ingredient_map())
    assert expected.to_dict() == {"fire": 1002, "water": 1998}
    assert page.summary.vector() == expected


def test_reagent_quantity_limit(window, ui_app) -> None:
    """Потолок количества в сумке — 9999."""
    from alchimist.core.elements import Element
    from alchimist.ui_qt.pages.reagents import MAX_REAGENT_QTY

    assert MAX_REAGENT_QTY == 9999

    ui_app.inventory.set_reagent("shcholkorekh", MAX_REAGENT_QTY)
    page = next(p for p in window.pages if isinstance(p, ReagentsPage))
    window.go_to(ReagentsPage)
    row = next(
        r
        for r in ui_app.inventory.reagent_rows(ui_app.catalog.ingredient_map())
        if r.ingredient.id == "shcholkorekh"
    )
    assert row.qty == 9999
    assert page.summary.vector()[Element.FIRE] == 9999
