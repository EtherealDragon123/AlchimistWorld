"""Найденное на полном разборе кода: то, что видно только в интерфейсе."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QComboBox

from alchimist.core.elements import ElementVector as EV
from alchimist.core.models import (
    ALL_BASES,
    Catalog,
    Ingredient,
    IngredientCategory,
    Potion,
    Rarity,
    Recipe,
    ResultKind,
)
from alchimist.services import build_app
from alchimist.ui_qt.main_window import MainWindow


def reagent(ident: str, name: str, rarity: Rarity, **elements: int) -> Ingredient:
    return Ingredient(
        id=ident,
        name=name,
        rarity=rarity,
        category=IngredientCategory.PLANT,
        elements=EV.from_dict(elements),
    )


# ── Сводная строка «Могу сварить» действует по тому, что показала ────────────
@pytest.fixture
def divergent_app(tmp_path, qapp):
    """Случай, где «самый простой» вариант и «самый дешёвый» — разные.

    Двойчатка одна даёт ровно две порции (Сл 12), а единственный способ сварить
    одну порцию — Глыба с довеском на три единицы (Сл 13).
    """
    potion = Potion(
        id="z",
        name="Зелье",
        rarity=Rarity.COMMON,
        recipe=Recipe(ALL_BASES, EV.from_dict({"fire": 1, "water": 1})),
    )
    items = [
        (reagent("dbl", "Двойчатка", Rarity.EPIC, fire=2, water=2), 1),
        (reagent("big", "Глыба", Rarity.LEGENDARY, fire=1, water=1, earth=3), 1),
    ]
    app = build_app(tmp_path)
    app.catalog.replace_all(Catalog([i for i, _q in items], [potion]))
    for ingredient, qty in items:
        app.inventory.set_reagent(ingredient.id, qty)
    return app


def test_can_brew_row_acts_on_the_option_it_shows(divergent_app, qapp) -> None:
    """В строке зелья — сложность самого простого варианта; кнопка варит его же."""
    from alchimist.ui_qt.pages.can_brew import ROLE_OPTION, CanBrewPage

    window = MainWindow(divergent_app)
    window.show()
    qapp.processEvents()
    window.go_to(CanBrewPage)
    page = next(p for p in window.pages if isinstance(p, CanBrewPage))
    page.max_excess.setValue(4)
    qapp.processEvents()

    item = page.tree.topLevelItem(0)
    option = item.data(0, ROLE_OPTION)
    assert item.text(3) == "12"
    assert option.difficulty.total == 12
    assert option.portions == 2
    window.close()


# ── Диалог варки подставляет найденное зелье ─────────────────────────────────
def test_brew_dialog_preselects_the_matching_potion(ui_app, qapp) -> None:
    """Qt отдаёт из `currentData()` строку, и сравнение `is` с `ResultKind` врало.

    Из-за этого диалог оставлял первое зелье по алфавиту, и варка могла уйти
    в журнал и в сумку под чужим именем.
    """
    from alchimist.ui_qt.dialogs.brew_dialog import BrewDialog

    # «Обычный Яд» далеко не первый по алфавиту: подмена была бы заметна.
    potion = ui_app.catalog.potion("obychnyy-yad")
    reagents = {"sopli-trollya": 1, "podlunnukh": 1}
    for ingredient_id, qty in reagents.items():
        ui_app.inventory.set_reagent(ingredient_id, qty)

    base = potion.recipe.sorted_bases()[0]
    hint = ui_app.brewing.hint(base, reagents)
    assert hint.matches and hint.matches[0].id == potion.id

    dialog = BrewDialog(ui_app, base, reagents, None, expected=None)
    qapp.processEvents()
    assert dialog.potion.currentData() == potion.id
    assert dialog.request().potion_id == potion.id
    dialog.deleteLater()


def test_brew_dialog_keeps_the_players_own_choice(ui_app, qapp) -> None:
    """Подстановка не должна перебивать того, кто выбрал зелье сам."""
    from alchimist.ui_qt.dialogs.brew_dialog import BrewDialog

    reagents = {"sopli-trollya": 1, "podlunnukh": 1}
    for ingredient_id, qty in reagents.items():
        ui_app.inventory.set_reagent(ingredient_id, qty)
    base = ui_app.catalog.potion("obychnyy-yad").recipe.sorted_bases()[0]
    dialog = BrewDialog(ui_app, base, reagents, None, expected=None)
    qapp.processEvents()
    index = dialog.potion.findData("barmaglot")
    dialog.potion.setCurrentIndex(index)
    qapp.processEvents()
    assert dialog.potion.currentData() == "barmaglot"
    dialog.deleteLater()


# ── Слияние справочников: «взять чужое» должно доходить до сервиса ───────────
def test_merge_choice_survives_qt(qapp) -> None:
    """`StrEnum` из `currentData()` возвращается обычной строкой."""
    from alchimist.core.models import coerce_enum
    from alchimist.services.exchange import MergeChoice

    combo = QComboBox()
    combo.addItem("оставить моё", MergeChoice.KEEP_MINE)
    combo.addItem("взять чужое", MergeChoice.TAKE_THEIRS)
    combo.setCurrentIndex(1)

    raw = combo.currentData()
    assert raw is not MergeChoice.TAKE_THEIRS  # вот почему нужен coerce_enum
    assert coerce_enum(MergeChoice, raw, MergeChoice.KEEP_MINE) is MergeChoice.TAKE_THEIRS


def test_result_kind_survives_qt(qapp) -> None:
    from alchimist.core.models import coerce_enum

    combo = QComboBox()
    combo.addItem("Известное зелье", ResultKind.KNOWN)
    assert combo.currentData() is not ResultKind.KNOWN
    assert coerce_enum(ResultKind, combo.currentData(), ResultKind.NONE) is ResultKind.KNOWN


# ── Значки тем не залёживаются на диске ──────────────────────────────────────
def test_indicator_cache_follows_the_palette(qapp) -> None:
    """Меняются цвета — меняется и путь, иначе на диске остаются старые значки."""
    from dataclasses import replace

    from alchimist.ui_qt.theme import DARK, LIGHT, indicator_paths

    dark = indicator_paths(DARK)
    light = indicator_paths(LIGHT)
    assert dark.keys() == light.keys()
    assert dark["check_on_plain"] != light["check_on_plain"]

    repainted = indicator_paths(replace(DARK, accent="#00ff00"))
    assert repainted["check_on_plain"] != dark["check_on_plain"]
