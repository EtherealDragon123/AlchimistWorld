from __future__ import annotations

import pytest

from alchimist.core.elements import ElementVector as EV
from alchimist.core.errors import AlchimistError, ErrorCode, WarningCode
from alchimist.core.models import (
    BaseType,
    Ingredient,
    IngredientCategory,
    Potion,
    Rarity,
    Recipe,
)
from alchimist.services.app import AppService
from alchimist.services.events import CatalogChanged, InventoryChanged


# ── справочник (FR-1.x, FR-2.x) ──────────────────────────────────────────────
def test_add_ingredient_warns_but_saves(app: AppService) -> None:
    """FR-1.4: несоответствие П-3.2 — предупреждение, не запрет."""
    ingredient, messages = app.add_ingredient(
        Ingredient(
            id="",
            name="Странный корень",
            rarity=Rarity.RARE,
            category=IngredientCategory.HERB,
            is_herb=True,
            elements=EV.from_dict({"earth": 1}),
        )
    )
    assert ingredient.id == "strannyy-koren"
    assert [m.code for m in messages] == [WarningCode.RARITY_UNITS_MISMATCH]
    assert app.catalog.ingredient("strannyy-koren").name == "Странный корень"


def test_duplicate_name_is_refused(app: AppService) -> None:
    """FR-1.4: название уникально — запрет."""
    with pytest.raises(AlchimistError) as excinfo:
        app.add_ingredient(Ingredient(id="", name="щёлкорех"))
    assert excinfo.value.code is ErrorCode.DUPLICATE_NAME


def test_empty_name_is_refused(app: AppService) -> None:
    with pytest.raises(AlchimistError) as excinfo:
        app.add_ingredient(Ingredient(id="", name="   "))
    assert excinfo.value.code is ErrorCode.EMPTY_NAME


def test_rename_keeps_id(app: AppService) -> None:
    """03 §6.9: при переименовании id не меняется."""
    ingredient = app.catalog.ingredient("shcholkorekh")
    updated, _ = app.update_ingredient(ingredient.copy(name="Щёлкорех обыкновенный"))
    assert updated.id == "shcholkorekh"
    assert updated.updated_at is not None


def test_delete_refused_when_in_inventory(app: AppService) -> None:
    """FR-1.5: то, что лежит в сумке, не удаляется."""
    app.inventory.set_reagent("shcholkorekh", 1)
    assert app.can_delete_ingredient("shcholkorekh") is False
    with pytest.raises(AlchimistError) as excinfo:
        app.delete_ingredient("shcholkorekh")
    assert excinfo.value.code is ErrorCode.INGREDIENT_IN_USE

    app.catalog.set_ingredient_hidden("shcholkorekh", True)
    assert app.catalog.ingredient("shcholkorekh").hidden is True
    assert "shcholkorekh" not in {i.id for i in app.catalog.ingredients()}


def test_delete_allowed_when_unused(app: AppService) -> None:
    app.delete_ingredient("fanana")
    assert "fanana" not in {i.id for i in app.catalog.ingredients()}


def test_delete_refused_after_journal_mention(app: AppService) -> None:
    from alchimist.core.models import Outcome, ResultKind
    from alchimist.services.brewing import BrewRequest

    app.inventory.set_reagent("shcholkorekh", 2)
    app.brewing.brew(
        BrewRequest(
            base=BaseType.LIQUID,
            reagents={"shcholkorekh": 2},
            outcome=Outcome.FAILURE,
            result_kind=ResultKind.NONE,
        )
    )
    assert app.inventory.reagent_qty("shcholkorekh") == 0
    assert app.can_delete_ingredient("shcholkorekh") is False


def test_hidden_ingredient_is_out_of_matching(app: AppService) -> None:
    app.inventory.set_reagent("shcholkorekh", 2)
    assert app.brewing.can_brew()
    app.catalog.set_ingredient_hidden("shcholkorekh", True)
    assert app.brewing.can_brew() == []


def test_set_recipe_reports_collision(app: AppService) -> None:
    """FR-2.5: коллизия видна сразу при вводе рецепта."""
    potion, _ = app.add_potion(Potion(id="", name="Ещё одна лазанья"))
    _, messages = app.set_recipe(
        potion.id, Recipe(frozenset({BaseType.LIQUID}), EV.from_dict({"earth": 2}))
    )
    assert [m.code for m in messages] == [WarningCode.RECIPE_COLLISION]


def test_clearing_recipe_removes_potion_from_matching(app: AppService) -> None:
    app.inventory.set_reagent("shcholkorekh", 2)
    assert {r.potion.id for r in app.brewing.can_brew()} == {"alkhimicheskiy-ogon"}
    app.set_recipe("alkhimicheskiy-ogon", None)
    assert app.brewing.can_brew() == []


def test_all_warnings_covers_catalog(app: AppService) -> None:
    app.add_ingredient(
        Ingredient(
            id="", name="Кривой корень", rarity=Rarity.EPIC, elements=EV.from_dict({"earth": 1})
        )
    )
    warnings = app.catalog.all_warnings()
    assert WarningCode.RARITY_UNITS_MISMATCH in {m.code for m in warnings["krivoy-koren"]}


# ── инвентарь (FR-3.x, FR-4.x) ───────────────────────────────────────────────
def test_quantity_shortcuts(app: AppService) -> None:
    """FR-3.2: +1 / −1 / ввод числа; при 0 строка исчезает."""
    assert app.inventory.add_reagent("fanana", 1) == 1
    assert app.inventory.add_reagent("fanana", 1) == 2
    app.inventory.set_reagent("fanana", 5)
    assert app.inventory.reagent_qty("fanana") == 5
    assert app.inventory.add_reagent("fanana", -10) == 0
    assert app.inventory.reagent_rows(app.catalog.ingredient_map()) == []


def test_notes_survive_quantity_changes(app: AppService) -> None:
    """FR-4.5: заметка к позиции инвентаря."""
    app.inventory.set_potion("zele-lecheniya-slaboe", 2, "у Гримли в сумке")
    app.inventory.add_potion("zele-lecheniya-slaboe", 1)
    rows = app.inventory.potion_rows(app.catalog.potion_map())
    assert rows[0].qty == 3
    assert rows[0].note == "у Гримли в сумке"


def test_element_summary(app: AppService) -> None:
    """FR-3.5: сводка по элементам."""
    app.inventory.set_reagent("shcholkorekh", 2)
    app.inventory.set_reagent("semya-nochnogo-plameni", 1)
    total = app.inventory.element_summary(app.catalog.ingredient_map())
    assert total.to_dict() == {"fire": 3, "dark": 2}


def test_events_reach_subscribers(app: AppService) -> None:
    """03 §2: сервисы сообщают об изменениях через шину."""
    seen: list[str] = []
    app.bus.subscribe(CatalogChanged, lambda e: seen.append("catalog"))
    app.bus.subscribe(InventoryChanged, lambda e: seen.append("inventory"))

    app.inventory.set_reagent("fanana", 1)
    app.update_ingredient(app.catalog.ingredient("fanana").copy(description="Вкусно"))
    assert seen == ["inventory", "catalog"]


def test_unsubscribe(app: AppService) -> None:
    seen: list[str] = []
    off = app.bus.subscribe(InventoryChanged, lambda e: seen.append("x"))
    app.inventory.set_reagent("fanana", 1)
    off()
    app.inventory.set_reagent("fanana", 2)
    assert seen == ["x"]


def test_unknown_ids_are_reported(app: AppService) -> None:
    """NFR-8: реагент пропал из справочника, инвентарь всё равно читается."""
    app.inventory.set_reagent("fanana", 1)
    # Обычным путём такое не удалить (FR-1.5), но файл справочника правят и руками.
    app.catalog.delete_ingredient("fanana")
    missing = app.inventory.unknown_ids(app.catalog.ingredient_map(), app.catalog.potion_map())
    assert missing == ["fanana"]
    assert app.inventory.reagent_rows(app.catalog.ingredient_map()) == []


def test_theme_is_persisted_across_restarts(app: AppService, tmp_path) -> None:
    """FR-9.5: приложение запоминает выбранную тему, а не откатывается на тёмную."""
    from alchimist.core.models import Theme
    from alchimist.services import build_app

    assert app.settings.theme is Theme.DARK

    app.settings.set_theme(Theme.LIGHT)
    assert build_app(tmp_path).settings.theme is Theme.LIGHT

    app.settings.set_theme(Theme.DARK)
    assert build_app(tmp_path).settings.theme is Theme.DARK
