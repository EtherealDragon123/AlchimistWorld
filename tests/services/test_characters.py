"""Персонажи, GM и изученные рецепты (FR-14.x) на справочнике кампании."""

from __future__ import annotations

import pytest

from alchimist.core.elements import ElementVector as EV
from alchimist.core.errors import AlchimistError, ErrorCode
from alchimist.core.models import (
    GM_ID,
    BaseType,
    Ingredient,
    Kit,
    Outcome,
    Rarity,
    Recipe,
    ResultKind,
    Role,
)
from alchimist.services import build_app
from alchimist.services.brewing import BrewRequest

#: Необычное зелье с рецептом: новичок его не знает, изучить можно.
SALAMANDER = "plamya-salamandry"
#: Редкое зелье без рецепта: не знает никто, изучать нечего.
INVISIBILITY = "zele-nevidimosti"


@pytest.fixture
def app(tmp_path):
    return build_app(tmp_path)


def error_code(call) -> ErrorCode:
    with pytest.raises(AlchimistError) as excinfo:
        call()
    return excinfo.value.code


# ── первый запуск (FR-14.1, FR-14.2) ─────────────────────────────────────────
def test_fresh_install_has_no_character_and_no_empty_profile(app, tmp_path) -> None:
    assert not app.characters.has_characters
    assert app.characters.active is None
    assert not (tmp_path / "profiles").exists()


def test_new_character_gets_catalog_and_common_recipes(app) -> None:
    ayn = app.create_character("Айн", (Kit.HERBALIST,))

    assert app.characters.active == ayn
    assert ayn.id == "ayn" and ayn.role is Role.PLAYER and ayn.kits == (Kit.HERBALIST,)
    assert app.settings.settings.active_profile == "ayn"
    assert len(app.catalog.catalog.ingredients) == 63
    assert len(app.catalog.catalog.potions) == 139
    common = {
        p.id
        for p in app.catalog.catalog.potions
        if p.rarity is Rarity.COMMON and p.recipe is not None
    }
    assert ayn.known_recipes == common
    assert len(common) == 20


def test_seed_keeps_gm_edits(app) -> None:
    """Встроенный справочник только дополняет: правки GM не затираются."""
    app.create_character("GM")
    potion = app.catalog.potion("alkhimicheskiy-ogon")
    app.update_potion(potion.copy(description_md="Правка мастера"))

    app.create_character("Айн")
    assert app.catalog.raw_potion("alkhimicheskiy-ogon").description_md == "Правка мастера"


# ── что видит игрок (FR-14.3, FR-14.8) ───────────────────────────────────────
def test_unlearned_recipe_is_hidden_from_the_player(app) -> None:
    app.create_character("Айн")
    assert app.catalog.potion(SALAMANDER).recipe is None
    assert app.catalog.potion_map()[SALAMANDER].recipe is None
    assert app.catalog.has_recipe(SALAMANDER)
    assert app.catalog.raw_potion(SALAMANDER).recipe is not None


def test_learning_and_forgetting_changes_what_can_be_brewed(app) -> None:
    app.create_character("Айн")
    app.inventory.set_reagent("shchelkorekh", 2)
    app.inventory.set_reagent("svechnaya-roza", 1)
    assert SALAMANDER not in {r.potion.id for r in app.brewing.can_brew()}

    app.learn_recipe(SALAMANDER)
    assert SALAMANDER in {r.potion.id for r in app.brewing.can_brew()}
    assert app.catalog.potion(SALAMANDER).recipe is not None

    app.forget_recipe(SALAMANDER)
    assert SALAMANDER not in {r.potion.id for r in app.brewing.can_brew()}


def test_learned_recipes_survive_restart(app, tmp_path) -> None:
    app.create_character("Айн")
    app.learn_recipe(SALAMANDER)
    fresh = build_app(tmp_path)
    assert fresh.characters.active.knows(SALAMANDER)
    assert fresh.catalog.potion(SALAMANDER).recipe is not None


def test_cannot_learn_what_nobody_knows(app) -> None:
    app.create_character("Айн")
    assert error_code(lambda: app.learn_recipe(INVISIBILITY)) is ErrorCode.RECIPE_UNKNOWN
    assert error_code(lambda: app.learn_recipe("net-takogo")) is ErrorCode.NOT_FOUND


def test_show_unknown_is_remembered(app, tmp_path) -> None:
    app.create_character("Айн")
    assert app.characters.active.show_unknown
    app.characters.set_show_unknown(False)
    assert not build_app(tmp_path).characters.active.show_unknown


# ── GM (FR-14.6) ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("name", ["GM", "gm", " Gm "])
def test_gm_is_added_by_name(app, name) -> None:
    app.create_character("Айн")
    gm = app.create_character(name)
    assert gm.id == GM_ID and gm.name == "GM" and gm.is_gm
    assert app.characters.active == gm
    assert app.can_edit_catalog
    assert app.catalog.potion(SALAMANDER).recipe is not None  # GM знает всё


def test_second_gm_is_the_same_gm(app) -> None:
    app.create_character("GM")
    app.create_character("Айн")
    again = app.create_character("gm")
    assert again.id == GM_ID
    assert [c.name for c in app.characters.characters()] == ["Айн", "GM"]


def test_player_cannot_change_the_catalog(app, tmp_path) -> None:
    app.create_character("Айн")
    ingredient = app.catalog.ingredient("shchelkorekh")
    potion = app.catalog.raw_potion(SALAMANDER)
    recipe = Recipe(frozenset({BaseType.LIQUID}), EV.from_dict({"fire": 1}))
    forbidden = [
        lambda: app.add_ingredient(Ingredient(id="", name="Пепел феникса")),
        lambda: app.update_ingredient(ingredient),
        lambda: app.delete_ingredient(ingredient.id),
        lambda: app.set_ingredient_hidden(ingredient.id, True),
        lambda: app.add_potion(potion.copy(id="", name="Новое зелье")),
        lambda: app.update_potion(potion),
        lambda: app.delete_potion(potion.id),
        lambda: app.set_potion_hidden(potion.id, True),
        lambda: app.set_recipe(potion.id, recipe),
        lambda: app.export_catalog(tmp_path / "out.json"),
    ]
    for call in forbidden:
        assert error_code(call) is ErrorCode.GM_ONLY
    # Ничего не поменялось: ни справочник, ни скрытый рецепт.
    assert app.catalog.raw_potion(SALAMANDER).recipe is not None


def test_player_can_accept_a_catalog_file_from_gm(app, tmp_path) -> None:
    app.create_character("GM")
    app.add_ingredient(Ingredient(id="", name="Пепел феникса", elements=EV.from_dict({"fire": 5})))
    path = app.export_catalog(tmp_path / "from-gm.json")

    player = build_app(tmp_path / "player")
    player.create_character("Гримли")
    assert "pepel-feniksa" not in player.catalog.ingredient_map()
    player.exchange.apply(player.exchange.plan(path))
    assert "pepel-feniksa" in player.catalog.ingredient_map()


def test_gm_does_not_need_to_learn(app) -> None:
    app.create_character("GM")
    app.forget_recipe(SALAMANDER)  # GM не забывает: ему справочник и есть знание
    assert app.catalog.potion(SALAMANDER).recipe is not None


# ── несколько персонажей (FR-14.5) ───────────────────────────────────────────
def test_each_character_has_own_inventory_kits_and_recipes(app, tmp_path) -> None:
    ayn = app.create_character("Айн", (Kit.HERBALIST,))
    app.inventory.set_reagent("shchelkorekh", 4)
    app.learn_recipe(SALAMANDER)

    grimli = app.create_character("Гримли", (Kit.POISONER,))
    assert app.inventory.reagent_qty("shchelkorekh") == 0
    assert app.characters.kits == (Kit.POISONER,)
    assert not grimli.knows(SALAMANDER)

    app.switch_character(ayn.id)
    assert app.inventory.reagent_qty("shchelkorekh") == 4
    assert app.characters.kits == (Kit.HERBALIST,)

    fresh = build_app(tmp_path)
    assert fresh.characters.active.id == ayn.id
    assert fresh.inventory.reagent_qty("shchelkorekh") == 4


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("", ErrorCode.EMPTY_NAME),
        ("  ", ErrorCode.EMPTY_NAME),
        ("айн", ErrorCode.DUPLICATE_NAME),
    ],
)
def test_bad_new_names(app, name, code) -> None:
    app.create_character("Айн")
    assert error_code(lambda: app.create_character(name)) is code


def test_rename(app) -> None:
    ayn = app.create_character("Айн")
    gm = app.create_character("GM")
    renamed = app.rename_character(ayn.id, "Айн Мудрый")
    assert renamed.id == ayn.id  # папка профиля та же
    assert error_code(lambda: app.rename_character(ayn.id, "gm")) is ErrorCode.NAME_RESERVED
    assert error_code(lambda: app.rename_character(gm.id, "Мастер")) is ErrorCode.NAME_RESERVED


def test_delete_moves_profile_aside_and_switches(app, tmp_path) -> None:
    ayn = app.create_character("Айн")
    assert error_code(lambda: app.delete_character(ayn.id)) is ErrorCode.LAST_CHARACTER

    grimli = app.create_character("Гримли")
    app.inventory.set_reagent("shchelkorekh", 1)
    app.delete_character(grimli.id)

    assert app.characters.active.id == ayn.id
    assert [c.name for c in app.characters.characters()] == ["Айн"]
    assert not (tmp_path / "profiles" / grimli.id).exists()
    kept = list((tmp_path / "deleted-profiles").glob("grimli-*"))
    assert len(kept) == 1 and (kept[0] / "inventory.json").exists()


# ── находка в лаборатории (FR-14.7) ──────────────────────────────────────────
def test_exact_brew_reveals_an_unlearned_recipe(app) -> None:
    app.create_character("Айн")
    salamander = Recipe(frozenset({BaseType.VISCOUS}), EV.from_dict({"fire": 2, "light": 1}))
    assert app.catalog.raw_potion(SALAMANDER).recipe == salamander

    found = app.catalog.unlearned_exact(BaseType.VISCOUS, salamander.elements)
    assert [p.id for p in found] == [SALAMANDER]
    # Не та основа, лишняя эссенция или две порции — не «ровно».
    assert app.catalog.unlearned_exact(BaseType.LIQUID, salamander.elements) == []
    excess = salamander.elements + EV.from_dict({"water": 1})
    assert app.catalog.unlearned_exact(BaseType.VISCOUS, excess) == []
    assert app.catalog.unlearned_exact(BaseType.VISCOUS, salamander.elements * 2) == []

    app.learn_recipe(SALAMANDER)
    assert app.catalog.unlearned_exact(BaseType.VISCOUS, salamander.elements) == []


def test_brew_by_an_unlearned_recipe_still_records(app) -> None:
    """Сварить можно и не зная рецепта: просто сложность по нему не считается."""
    app.create_character("Айн")
    app.inventory.set_reagent("shchelkorekh", 2)
    app.inventory.set_reagent("svechnaya-roza", 1)
    outcome = app.brewing.brew(
        BrewRequest(
            base=BaseType.VISCOUS,
            reagents={"shchelkorekh": 2, "svechnaya-roza": 1},
            outcome=Outcome.SUCCESS,
            result_kind=ResultKind.NEW,
            potion_id=SALAMANDER,
        )
    )
    assert outcome.entry.difficulty is None
    assert app.inventory.potion_qty(SALAMANDER) == 1
    assert app.catalog.unlearned_exact(*outcome.entry.combination_key)[0].id == SALAMANDER


# ── перенос со старой версии (03 §6.12) ──────────────────────────────────────
def test_legacy_profile_becomes_a_character(tmp_path, campaign_file) -> None:
    old = build_app(tmp_path)
    old.exchange.apply(old.exchange.plan(campaign_file))
    old.inventory.set_reagent("shchelkorekh", 3)  # без персонажа пишет в profiles/default
    (tmp_path / "settings.toml").write_text(
        'kits = ["herbalist", "poisoner"]\ncharacter_name = "Айн"\nactive_profile = "default"\n',
        encoding="utf-8",
    )

    app = build_app(tmp_path)
    ayn = app.characters.active
    assert (ayn.id, ayn.name, ayn.kits) == ("default", "Айн", (Kit.HERBALIST, Kit.POISONER))
    assert ayn.known_recipes == app.catalog.recipe_ids()  # знал всё — знает и дальше
    assert app.inventory.reagent_qty("shchelkorekh") == 3

    app.settings.set_theme(app.settings.theme)
    text = (tmp_path / "settings.toml").read_text(encoding="utf-8")
    assert "character_name" not in text and "kits" not in text
    assert build_app(tmp_path).characters.active.name == "Айн"
