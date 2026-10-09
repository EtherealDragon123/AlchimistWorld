"""Изучение реагентов (FR-14.9–14.11) на справочнике кампании."""

from __future__ import annotations

import json

import pytest

from alchimist.core.elements import ElementVector as EV
from alchimist.core.errors import AlchimistError, ErrorCode
from alchimist.core.models import BaseType, Ingredient, IngredientCategory, Outcome, Rarity
from alchimist.services import build_app
from alchimist.services.brewing import BrewRequest
from alchimist.services.distilling import EXTRACT_ID

#: Необычное растение: новичок его не знает.
KAVA = "koren-kavy"
#: Редкое существо.
HAG_BLOOD = "krov-ozernoy-kargi"
#: Обычное растение: его знают все.
NUT = "shchelkorekh"
#: Необычное растение, из которого дистилляция делает эссенцию земли.
STEEL_SAP = "sok-stalnogo-dereva"
#: Все реагенты, которых новичок не знает (П-3.1: редкость выше обычной и не эссенция).
UNKNOWN_TO_NEWCOMER = {
    KAVA,
    HAG_BLOOD,
    STEEL_SAP,
    "krov-drakocherepakhi",
    "krov-umertviya",
    "ledyanaya-loza",
    "semya-nochnogo-plameni",
    "volosy-ozernoy-kargi",
}


@pytest.fixture
def app(tmp_path):
    app = build_app(tmp_path)
    app.create_character("Айн")
    return app


def known_ids(app) -> set[str]:
    return {i.id for i in app.catalog.catalog.ingredients if app.catalog.knows_ingredient(i.id)}


def error_code(call) -> ErrorCode:
    with pytest.raises(AlchimistError) as excinfo:
        call()
    return excinfo.value.code


# ── что знает новичок (FR-14.2) ──────────────────────────────────────────────
def test_newcomer_knows_common_reagents_and_all_essences(app) -> None:
    everything = {i.id for i in app.catalog.catalog.ingredients}
    assert len(everything) == 63
    assert everything - known_ids(app) == UNKNOWN_TO_NEWCOMER
    assert len(known_ids(app)) == 55
    assert app.characters.active.known_ingredients == frozenset()


def test_unknown_reagent_is_seen_without_elements(app) -> None:
    view = app.catalog.ingredient(KAVA)
    assert view.name == "Корень кавы" and view.rarity is Rarity.UNCOMMON
    assert view.elements.is_empty
    assert app.catalog.ingredient_map()[KAVA].elements.is_empty
    assert next(i for i in app.catalog.ingredients() if i.id == KAVA).elements.is_empty
    # Сам справочник не тронут: им пользуются GM, обмен и проверки.
    assert app.catalog.raw_ingredient(KAVA).elements == EV.from_dict({"water": 1, "magic": 1})
    assert app.catalog.catalog.ingredient_by_id(KAVA).elements == EV.from_dict(
        {"water": 1, "magic": 1}
    )
    # Ни подсказка «в каких рецептах участвует», ни «чем закрыть» его не выдают.
    assert app.brewing.recipes_using(view) == []
    assert KAVA not in {i.id for i in app.catalog.known_ingredients_list()}


def test_gm_and_no_character_know_everything(tmp_path) -> None:
    bare = build_app(tmp_path / "bare")  # консоль на пустой папке, без персонажа
    assert bare.characters.known_ingredient_ids() is None
    gm_app = build_app(tmp_path / "gm")
    gm_app.create_character("GM")
    assert known_ids(gm_app) == {i.id for i in gm_app.catalog.catalog.ingredients}
    assert not gm_app.catalog.ingredient(KAVA).elements.is_empty


# ── изучить и забыть (FR-14.9) ───────────────────────────────────────────────
def test_learn_and_forget(app, tmp_path) -> None:
    app.learn_ingredient(KAVA)
    assert app.catalog.knows_ingredient(KAVA)
    assert app.catalog.ingredient(KAVA).elements == EV.from_dict({"water": 1, "magic": 1})
    # Изученное переживает перезапуск.
    assert build_app(tmp_path).catalog.knows_ingredient(KAVA)

    app.forget_ingredient(KAVA)
    assert not app.catalog.knows_ingredient(KAVA)
    assert not build_app(tmp_path).catalog.knows_ingredient(KAVA)


def test_starter_reagents_are_not_stored_and_not_forgotten(app) -> None:
    app.learn_ingredient(NUT)
    assert app.characters.active.known_ingredients == frozenset()
    app.forget_ingredient(NUT)
    assert app.catalog.knows_ingredient(NUT)


def test_unknown_id_is_reported(app) -> None:
    assert error_code(lambda: app.learn_ingredient("net-takogo")) is ErrorCode.NOT_FOUND
    assert error_code(lambda: app.forget_ingredient("net-takogo")) is ErrorCode.NOT_FOUND


# ── попал в сумку — изучен (FR-14.10) ────────────────────────────────────────
def test_reagent_in_the_bag_becomes_known_for_good(app) -> None:
    app.inventory.set_reagent(HAG_BLOOD, 1)
    assert app.catalog.knows_ingredient(HAG_BLOOD)
    app.inventory.set_reagent(HAG_BLOOD, 0)
    assert app.catalog.knows_ingredient(HAG_BLOOD)


def test_reagent_in_the_bag_cannot_be_forgotten(app) -> None:
    app.inventory.set_reagent(KAVA, 2)
    assert error_code(lambda: app.forget_ingredient(KAVA)) is ErrorCode.INGREDIENT_IN_BAG
    assert app.catalog.knows_ingredient(KAVA)
    app.inventory.set_reagent(KAVA, 0)
    app.forget_ingredient(KAVA)
    assert not app.catalog.knows_ingredient(KAVA)


def test_undone_brew_returns_and_teaches_the_reagent(app) -> None:
    app.inventory.set_reagent(KAVA, 1)
    outcome = app.brewing.brew(
        BrewRequest(base=BaseType.LIQUID, reagents={KAVA: 1}, outcome=Outcome.FAILURE)
    )
    app.forget_ingredient(KAVA)
    assert not app.catalog.knows_ingredient(KAVA)

    app.brewing.undo_brew(outcome.entry.id)
    assert app.inventory.reagent_qty(KAVA) == 1
    assert app.catalog.knows_ingredient(KAVA)


def test_undone_distillation_returns_and_teaches_the_reagent(app) -> None:
    app.inventory.set_potion(EXTRACT_ID, 1)
    app.inventory.set_reagent(STEEL_SAP, 1)
    entry = app.distilling.distill({STEEL_SAP: 1})
    app.forget_ingredient(STEEL_SAP)

    app.distilling.undo(entry.id)
    assert app.inventory.reagent_qty(STEEL_SAP) == 1
    assert app.catalog.knows_ingredient(STEEL_SAP)


def test_hand_edited_bag_is_learned_on_start_and_on_switch(app, tmp_path) -> None:
    """Сумку поправили руками: всё, что в ней лежит, изучается при открытии."""
    data = {
        "schema_version": 1,
        "reagents": [{"ingredient_id": KAVA, "qty": 1, "note": ""}],
        "potions": [],
    }
    bag = tmp_path / "profiles" / "ayn" / "inventory.json"
    bag.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert build_app(tmp_path).catalog.knows_ingredient(KAVA)

    other = build_app(tmp_path)
    other.create_character("Борин")
    other_bag = tmp_path / "profiles" / "borin" / "inventory.json"
    other_bag.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    other.switch_character("ayn")
    other.switch_character("borin")
    assert other.catalog.knows_ingredient(KAVA)


# ── подбор (FR-14.11) ────────────────────────────────────────────────────────
def test_almost_ready_does_not_suggest_unknown_reagents(app) -> None:
    """«Чем закрыть» не выдаёт неизученное: игрок не знает, что в нём."""
    gm = build_app(app.paths.root)
    gm.create_character("GM")
    gm.add_ingredient(
        Ingredient(
            id="",
            name="Пепел феникса",
            rarity=Rarity.UNCOMMON,
            category=IngredientCategory.CREATURE,
            elements=EV.from_dict({"fire": 1, "light": 1}),
        )
    )
    app.reload()
    app.learn_recipe("plamya-salamandry")  # вязкая, огонь 2 + свет 1
    app.inventory.set_reagent(NUT, 1)  # огонь 1: не хватает огня 1 и света 1

    def fillers() -> set[str]:
        row = next(r for r in app.brewing.almost() if r.potion.id == "plamya-salamandry")
        return {pick.ingredient.id for filler in row.fillers for pick in filler.picks}

    assert "pepel-feniksa" not in fillers()
    app.learn_ingredient("pepel-feniksa")
    app.brewing.invalidate()
    assert "pepel-feniksa" in fillers()


# ── перенос со старой версии (03 §6.11) ──────────────────────────────────────
def test_character_from_older_version_knows_every_reagent(app, tmp_path) -> None:
    path = tmp_path / "profiles" / "ayn" / "character.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema_version"] = 1
    del data["known_ingredients"]
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    reopened = build_app(tmp_path)
    assert known_ids(reopened) == {i.id for i in reopened.catalog.catalog.ingredients}
    rewritten = json.loads(path.read_text(encoding="utf-8"))
    assert rewritten["schema_version"] == 2
    assert len(rewritten["known_ingredients"]) == 63
    assert (path.parent / "character.json.v1.bak").exists()
