"""Сценарии из ТЗ (02 §3) на справочнике настоящей кампании.

Играет обычный персонаж, как в жизни: он знает рецепты обычных зелий, остальные
изучает сам (FR-14.3). Справочник правит GM — в сценариях это видно явно.
"""

from __future__ import annotations

import pytest

from alchimist.core.elements import ElementVector as EV
from alchimist.core.errors import AlchimistError, ErrorCode, WarningCode
from alchimist.core.models import (
    BaseType,
    Ingredient,
    IngredientCategory,
    Kit,
    Outcome,
    Rarity,
    Recipe,
    ResultKind,
)
from alchimist.services import build_app
from alchimist.services.brewing import BrewRequest


@pytest.fixture
def app(tmp_path):
    """Первый запуск: персонаж создан, справочник заполнен встроенным (FR-14.1, FR-14.2)."""
    service = build_app(tmp_path)
    service.create_character("Айн")
    return service


def as_gm(app):
    """Переключиться на GM: справочник меняет только он (FR-14.6)."""
    return app.create_character("GM")


def test_c1_after_session(app) -> None:
    """С-1: персонаж набрал трав — игрок находит их поиском и прибавляет количество."""
    found = [i for i in app.catalog.ingredients() if "фанан" in i.name.casefold()]
    assert [i.name for i in found] == ["Фанана"]

    app.inventory.add_reagent(found[0].id, 3)
    app.inventory.add_reagent("khitrost-shefa", 2)
    rows = {
        r.ingredient.name: r.qty for r in app.inventory.reagent_rows(app.catalog.ingredient_map())
    }
    assert rows == {"Фанана": 3, "Хитрость Шефа": 2}


def test_c2_what_can_i_brew(app) -> None:
    """С-2: главный экран показывает зелья с конкретными реагентами и числом повторов."""
    app.inventory.set_reagent("shchelkorekh", 4)
    app.inventory.set_reagent("svechnaya-roza", 2)

    rows = {row.potion.name: row for row in app.brewing.can_brew()}
    assert "Алхимический Огонь" in rows
    assert rows["Алхимический Огонь"].max_repeats == 2
    best = rows["Алхимический Огонь"].best
    assert [(p.ingredient.name, p.count) for p in best.combination.picks] == [("Щёлкорех", 2)]

    # Рецепт необычного зелья персонаж ещё не изучил — подбор его не видит (FR-14.8).
    assert "Пламя Саламандры" not in rows
    app.learn_recipe("plamya-salamandry")
    rows = {row.potion.name: row for row in app.brewing.can_brew()}
    assert "Пламя Саламандры" in rows
    assert rows["Пламя Саламандры"].best.base is BaseType.VISCOUS


def test_c3_brewing(app) -> None:
    """С-3: сварить, отметить успех, увидеть списание, зелье и запись журнала."""
    app.inventory.set_reagent("podlunnukh", 1)
    app.inventory.set_reagent("svechnaya-roza", 1)
    row = next(r for r in app.brewing.can_brew() if r.potion.name == "Зелье Лечения (Слабое)")
    option = row.best

    app.brewing.brew(
        BrewRequest(
            base=option.base,
            reagents=option.combination.as_map(),
            outcome=Outcome.SUCCESS,
            result_kind=ResultKind.KNOWN,
            potion_id=row.potion.id,
        )
    )
    assert app.inventory.reagent_qty("podlunnukh") == 0
    assert app.inventory.potion_qty(row.potion.id) == 1
    assert len(app.journal.entries()) == 1
    assert app.brewing.can_brew() == []


def test_c4_experiment(app) -> None:
    """С-4: в лаборатории собрали комбинацию, получили новое зелье, сохранили рецепт.

    Новое зелье и его рецепт — правка справочника, поэтому эксперимент ставит GM.
    """
    as_gm(app)
    app.inventory.set_reagent("fanana", 2)
    app.inventory.set_reagent("sopli-trollya", 2)

    hint = app.brewing.hint(BaseType.VISCOUS, {"fanana": 1, "sopli-trollya": 1})
    assert hint.elements.to_dict() == {"air": 1, "water": 1}
    assert hint.matches == ()
    assert not hint.was_tried

    new_potion, _messages = app.add_potion(
        __import__("alchimist.core.models", fromlist=["Potion"]).Potion(
            id="", name="Зелье Болотного Ветра", rarity=Rarity.COMMON
        )
    )
    outcome = app.brewing.brew(
        BrewRequest(
            base=BaseType.VISCOUS,
            reagents={"fanana": 1, "sopli-trollya": 1},
            result_kind=ResultKind.NEW,
            potion_id=new_potion.id,
        )
    )
    saved, messages = app.save_as_recipe(outcome.entry.id)
    assert saved.recipe.elements.to_dict() == {"air": 1, "water": 1}
    assert messages == []

    # Теперь комбинация узнаётся, а журнал помнит попытку.
    hint = app.brewing.hint(BaseType.VISCOUS, {"fanana": 1, "sopli-trollya": 1})
    assert [p.name for p in hint.matches] == ["Зелье Болотного Ветра"]
    assert hint.was_tried


def test_c5_new_reagent_from_dm(app) -> None:
    """С-5: DM выдал реагент — игрок его не заводит, это делает GM (FR-14.6)."""
    pepel = Ingredient(id="", name="Пепел феникса", elements=EV.from_dict({"fire": 5}))
    with pytest.raises(AlchimistError) as excinfo:
        app.add_ingredient(pepel)
    assert excinfo.value.code is ErrorCode.GM_ONLY

    as_gm(app)
    ingredient, messages = app.add_ingredient(
        Ingredient(
            id="",
            name="Пепел феникса",
            rarity=Rarity.LEGENDARY,
            category=IngredientCategory.CREATURE,
            elements=EV.from_dict({"fire": 5}),
            habitats=["Горы"],
            description="Остался от очень плохого дня.",
        )
    )
    assert ingredient.id == "pepel-feniksa"
    assert messages == []
    app.reload()
    assert app.catalog.ingredient("pepel-feniksa").habitats == ["Горы"]


def test_c6_learned_recipe(app) -> None:
    """С-6: купили рецепт — GM вписал его в справочник, игрок изучил (FR-14.3)."""
    player = app.characters.active
    potion = next(p for p in app.catalog.potions() if p.name == "Зелье Невидимости")
    assert potion.recipe is None
    with pytest.raises(AlchimistError) as excinfo:
        app.learn_recipe(potion.id)  # рецепта нет даже в справочнике — учить нечего
    assert excinfo.value.code is ErrorCode.RECIPE_UNKNOWN

    as_gm(app)
    _saved, messages = app.set_recipe(
        potion.id, Recipe(frozenset({BaseType.LIQUID}), EV.from_dict({"dark": 2, "magic": 2}))
    )
    assert messages == []  # редкое зелье, 4 единицы — П-5.2 выполняется

    # А вот занятый ключ даёт предупреждение (П-5.6), а заодно и размер не сходится (П-5.2).
    _saved, messages = app.set_recipe(
        potion.id, Recipe(frozenset({BaseType.LIQUID}), EV.from_dict({"earth": 2}))
    )
    codes = {m.code for m in messages}
    assert codes == {WarningCode.RECIPE_SIZE_MISMATCH, WarningCode.RECIPE_COLLISION}
    collision = next(m for m in messages if m.code is WarningCode.RECIPE_COLLISION)
    assert collision.params["others"] == ["Зелье Лазанья"]

    # Игрок рецепта пока не знает: в справочнике он есть, но не изучен.
    app.switch_character(player.id)
    assert app.catalog.potion(potion.id).recipe is None
    assert app.catalog.has_recipe(potion.id)
    app.learn_recipe(potion.id)
    assert app.catalog.potion(potion.id).recipe.elements.to_dict() == {"earth": 2}


def test_c7_party_exchange(app, tmp_path) -> None:
    """С-7: GM выгружает справочник в файл, тот приезжает к другому игроку."""
    as_gm(app)
    app.add_ingredient(
        Ingredient(
            id="", name="Пепел феникса", rarity=Rarity.LEGENDARY, elements=EV.from_dict({"fire": 5})
        )
    )
    path = app.export_catalog(tmp_path / "catalog.json")

    other = build_app(tmp_path / "other")
    plan = other.exchange.plan(path)
    assert len(plan.added) == 64 + 139
    other.exchange.apply(plan)
    assert other.catalog.ingredient("pepel-feniksa").rarity is Rarity.LEGENDARY
    assert len(other.catalog.potions()) == 139


def test_c8_using_a_potion(app) -> None:
    """С-8: выпили зелье — количество уменьшилось, в журнале запись."""
    app.inventory.set_potion("zele-lecheniya-slaboe", 2)
    app.brewing.use_potion("zele-lecheniya-slaboe", 1, "в бою с троллем")
    assert app.inventory.potion_qty("zele-lecheniya-slaboe") == 1
    assert app.journal.entries()[0].note == "в бою с троллем"


def test_c9_what_is_missing(app) -> None:
    """С-9: «Пламя Саламандры: не хватает Свет×1» и чем это закрыть."""
    app.learn_recipe("plamya-salamandry")
    app.inventory.set_reagent("shchelkorekh", 2)
    row = next(r for r in app.brewing.almost() if r.potion.name == "Пламя Саламандры")
    assert row.missing.to_dict() == {"light": 1}
    fillers = {p.ingredient.name for f in row.fillers for p in f.picks}
    assert "Свечная Роза" in fillers
    assert "Мыльная Трава" in fillers


def test_kits_change_the_whole_picture(app) -> None:
    """П-6.3 на реальных данных."""
    app.inventory.set_reagent("tusklaya-essentsiya-ognya", 1)
    app.inventory.set_reagent("shchelkorekh", 2)
    app.inventory.set_reagent("podlunnukh", 1)
    app.inventory.set_reagent("tkanevyy-list", 1)

    everything = {r.potion.name for r in app.brewing.can_brew()}
    assert "Кислота" in everything  # взрывная основа
    assert "Алхимический Огонь" in everything

    app.set_kits((Kit.HERBALIST,))
    herbalist = {r.potion.name for r in app.brewing.can_brew()}
    assert "Кислота" not in herbalist  # взрывная основа травнику недоступна
    assert "Алхимический Огонь" in herbalist  # но из двух Щёлкорехов — можно

    app.set_kits((Kit.POISONER,))
    poisons = {r.potion.kind.value for r in app.brewing.can_brew()}
    assert poisons <= {"poison"}


def test_data_survives_restart(app, tmp_path) -> None:
    """Всё, что наменяли, лежит в файлах и читается заново."""
    app.inventory.set_reagent("shchelkorekh", 2)
    app.brewing.brew(
        BrewRequest(
            base=BaseType.LIQUID,
            reagents={"shchelkorekh": 2},
            result_kind=ResultKind.KNOWN,
            potion_id="alkhimicheskiy-ogon",
            note="до перезапуска",
        )
    )
    app.set_kits((Kit.HERBALIST, Kit.POISONER))

    fresh = build_app(tmp_path)
    assert fresh.inventory.potion_qty("alkhimicheskiy-ogon") == 1
    assert fresh.journal.entries()[0].note == "до перезапуска"
    assert fresh.characters.active.name == "Айн"
    assert fresh.characters.kits == (Kit.HERBALIST, Kit.POISONER)
    assert len(fresh.catalog.ingredients()) == 63
