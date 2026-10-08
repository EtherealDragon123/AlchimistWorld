from __future__ import annotations

import pytest

from alchimist.core.elements import ElementVector as EV
from alchimist.core.errors import AlchimistError, ErrorCode, WarningCode
from alchimist.core.models import (
    BaseType,
    JournalEntryType,
    Kit,
    Outcome,
    ResultKind,
)
from alchimist.services.app import AppService
from alchimist.services.brewing import BrewRequest


def test_brew_moves_everything_at_once(app: AppService) -> None:
    """FR-7.2: реагенты списаны, зелье добавлено, запись в журнале."""
    app.inventory.set_reagent("podlunnukh", 2)
    app.inventory.set_reagent("svechnaya-roza", 1)

    outcome = app.brewing.brew(
        BrewRequest(
            base=BaseType.LIQUID,
            reagents={"podlunnukh": 1, "svechnaya-roza": 1},
            outcome=Outcome.SUCCESS,
            result_kind=ResultKind.KNOWN,
            potion_id="zele-lecheniya-slaboe",
        )
    )

    assert app.inventory.reagent_qty("podlunnukh") == 1
    assert app.inventory.reagent_qty("svechnaya-roza") == 0
    assert app.inventory.potion_qty("zele-lecheniya-slaboe") == 1

    entry = outcome.entry
    assert entry.type is JournalEntryType.BREW
    assert entry.base is BaseType.LIQUID
    assert entry.elements.to_dict() == {"light": 1, "dark": 1}
    assert entry.result.potion_id == "zele-lecheniya-slaboe"
    assert app.journal.entries() == [entry]

    # Данные действительно на диске.
    app.reload()
    assert app.inventory.potion_qty("zele-lecheniya-slaboe") == 1
    assert len(app.journal.entries()) == 1


def test_failed_brew_consumes_reagents_and_gives_nothing(app: AppService) -> None:
    """П-7.2: при провале реагенты списываются, зелья нет."""
    app.inventory.set_reagent("shcholkorekh", 2)
    app.brewing.brew(
        BrewRequest(
            base=BaseType.LIQUID,
            reagents={"shcholkorekh": 2},
            outcome=Outcome.FAILURE,
        )
    )
    assert app.inventory.reagent_qty("shcholkorekh") == 0
    assert app.inventory.potion_qty("alkhimicheskiy-ogon") == 0
    entry = app.journal.entries()[0]
    assert entry.outcome is Outcome.FAILURE
    assert entry.result.kind is ResultKind.NONE
    assert entry.yield_qty == 0


def test_brew_yield_can_be_more_than_one(app: AppService) -> None:
    """П-7.3: количество продукта правится перед подтверждением."""
    app.inventory.set_reagent("shcholkorekh", 2)
    app.brewing.brew(
        BrewRequest(
            base=BaseType.LIQUID,
            reagents={"shcholkorekh": 2},
            result_kind=ResultKind.KNOWN,
            potion_id="alkhimicheskiy-ogon",
            yield_qty=3,
        )
    )
    assert app.inventory.potion_qty("alkhimicheskiy-ogon") == 3


def test_brew_without_reagents_is_refused(app: AppService) -> None:
    with pytest.raises(AlchimistError) as excinfo:
        app.brewing.brew(BrewRequest(base=BaseType.LIQUID, reagents={}))
    assert excinfo.value.code is ErrorCode.NO_REAGENTS


def test_brew_without_stock_changes_nothing(app: AppService) -> None:
    app.inventory.set_reagent("shcholkorekh", 1)
    with pytest.raises(AlchimistError) as excinfo:
        app.brewing.brew(BrewRequest(base=BaseType.LIQUID, reagents={"shcholkorekh": 2}))
    assert excinfo.value.code is ErrorCode.NOT_ENOUGH_REAGENTS
    assert app.inventory.reagent_qty("shcholkorekh") == 1
    assert app.journal.entries() == []


def test_undo_restores_everything(app: AppService) -> None:
    """FR-7.6: вернуть реагенты, убрать зелье, пометить запись отменённой."""
    app.inventory.set_reagent("podlunnukh", 1)
    app.inventory.set_reagent("svechnaya-roza", 1)
    outcome = app.brewing.brew(
        BrewRequest(
            base=BaseType.LIQUID,
            reagents={"podlunnukh": 1, "svechnaya-roza": 1},
            result_kind=ResultKind.KNOWN,
            potion_id="zele-lecheniya-slaboe",
        )
    )

    undone = app.brewing.undo_brew(outcome.entry.id)
    assert undone.undone is True
    assert app.inventory.reagent_qty("podlunnukh") == 1
    assert app.inventory.reagent_qty("svechnaya-roza") == 1
    assert app.inventory.potion_qty("zele-lecheniya-slaboe") == 0
    # Отменённая варка не мешает подсказке «уже пробовали».
    assert app.journal.combination_history(BaseType.LIQUID, undone.elements) == []


def test_use_potion(app: AppService) -> None:
    """FR-4.2: −1 шт. и запись в журнал."""
    app.inventory.set_potion("zele-lecheniya-slaboe", 2)
    app.brewing.use_potion("zele-lecheniya-slaboe")
    assert app.inventory.potion_qty("zele-lecheniya-slaboe") == 1
    entry = app.journal.entries()[0]
    assert entry.type is JournalEntryType.USE
    assert entry.qty == 1


def test_use_more_than_available(app: AppService) -> None:
    with pytest.raises(AlchimistError) as excinfo:
        app.brewing.use_potion("zele-lecheniya-slaboe")
    assert excinfo.value.code is ErrorCode.NOT_ENOUGH_POTIONS


# ── лаборатория (FR-7.3–7.5) ─────────────────────────────────────────────────
def test_lab_hint_matches_known_recipe(app: AppService) -> None:
    app.inventory.set_reagent("tkanevyy-list", 2)
    hint = app.brewing.hint(BaseType.LIQUID, {"tkanevyy-list": 2})
    assert hint.elements.to_dict() == {"earth": 2}
    assert [p.name for p in hint.matches] == ["Зелье Лазанья"]
    assert not hint.was_tried


def test_lab_hint_remembers_previous_attempt(app: AppService) -> None:
    """П-7.6: «эту комбинацию уже пробовали»."""
    app.inventory.set_reagent("sopli-trollya", 2)
    app.brewing.brew(
        BrewRequest(
            base=BaseType.EXPLOSIVE,
            reagents={"sopli-trollya": 2},
            result_kind=ResultKind.NOTHING,
        )
    )
    hint = app.brewing.hint(BaseType.EXPLOSIVE, {"sopli-trollya": 2})
    assert hint.matches == ()
    assert hint.was_tried
    assert hint.history[0].result.kind is ResultKind.NOTHING


def test_lab_hint_knows_which_kit_allows_it(app: AppService, play_as) -> None:
    play_as(kits=(Kit.HERBALIST,))
    hint = app.brewing.hint(BaseType.EXPLOSIVE, {"shcholkorekh": 2})
    assert hint.allowed_kits == ()  # травнику взрывная основа недоступна
    hint = app.brewing.hint(BaseType.LIQUID, {"tusklaya-essentsiya-ognya": 1})
    assert hint.allowed_kits == ()  # и эссенции тоже
    hint = app.brewing.hint(BaseType.LIQUID, {"shcholkorekh": 2})
    assert hint.allowed_kits == (Kit.HERBALIST,)


def test_save_as_recipe_from_journal(app: AppService) -> None:
    """П-7.5: одной кнопкой комбинация становится рецептом."""
    app.inventory.set_reagent("sopli-trollya", 1)
    app.inventory.set_reagent("fanana", 1)
    potion, _ = app.catalog.add_potion(
        __import__("alchimist.core.models", fromlist=["Potion"]).Potion(
            id="novoe-zele", name="Новое зелье"
        )
    )
    outcome = app.brewing.brew(
        BrewRequest(
            base=BaseType.VISCOUS,
            reagents={"sopli-trollya": 1, "fanana": 1},
            result_kind=ResultKind.NEW,
            potion_id=potion.id,
        )
    )
    saved, messages = app.brewing.save_as_recipe(outcome.entry.id)
    assert saved.recipe.bases == frozenset({BaseType.VISCOUS})
    assert saved.recipe.elements.to_dict() == {"water": 1, "air": 1}
    # П-5.2: у обычного зелья должно быть 2 единицы — здесь ровно 2, предупреждений нет.
    assert messages == []


def test_save_as_recipe_reports_collision(app: AppService) -> None:
    app.inventory.set_reagent("tkanevyy-list", 2)
    potion, _ = app.catalog.add_potion(
        __import__("alchimist.core.models", fromlist=["Potion"]).Potion(
            id="dvoynik", name="Двойник"
        )
    )
    outcome = app.brewing.brew(
        BrewRequest(
            base=BaseType.LIQUID,
            reagents={"tkanevyy-list": 2},
            result_kind=ResultKind.NEW,
            potion_id=potion.id,
        )
    )
    _, messages = app.brewing.save_as_recipe(outcome.entry.id)
    assert [m.code for m in messages] == [WarningCode.RECIPE_COLLISION]
    assert messages[0].params["others"] == ["Зелье Лазанья"]


# ── FR-5.5 пересчёт ──────────────────────────────────────────────────────────
def test_can_brew_updates_after_inventory_change(app: AppService) -> None:
    assert app.brewing.can_brew() == []
    app.inventory.set_reagent("shcholkorekh", 2)
    assert [row.potion.id for row in app.brewing.can_brew()] == ["alkhimicheskiy-ogon"]
    app.inventory.set_reagent("shcholkorekh", 0)
    assert app.brewing.can_brew() == []


def test_can_brew_updates_after_recipe_change(app: AppService) -> None:
    from alchimist.core.models import Recipe

    app.inventory.set_reagent("sopli-trollya", 2)
    assert [r.potion.id for r in app.brewing.can_brew()] == []

    app.set_recipe("barmaglot", Recipe(frozenset({BaseType.LIQUID}), EV.from_dict({"water": 2})))
    assert "barmaglot" in {r.potion.id for r in app.brewing.can_brew()}


def test_kits_affect_can_brew(app: AppService, play_as) -> None:
    play_as()
    app.inventory.set_reagent("tusklaya-essentsiya-ognya", 1)
    assert {r.potion.id for r in app.brewing.can_brew()} == {"alkhimicheskiy-ogon"}

    app.set_kits((Kit.HERBALIST,))
    assert app.brewing.can_brew() == []


def test_almost_ready_through_service(app: AppService) -> None:
    app.inventory.set_reagent("shcholkorekh", 2)
    rows = {row.potion.id: row for row in app.brewing.almost()}
    assert rows["plamya-salamandry"].missing.to_dict() == {"light": 1}
    assert "alkhimicheskiy-ogon" not in rows  # оно уже варится


def test_recipes_using_ingredient(app: AppService) -> None:
    """FR-1.6: в каких рецептах реагент может участвовать."""
    ingredient = app.catalog.ingredient("shcholkorekh")
    names = {p.name for p in app.brewing.recipes_using(ingredient)}
    assert "Алхимический Огонь" in names
    assert "Зелье Силы Огра" in names
    assert "Зелье Лазанья" not in names


# ── П-8: порции, лишние эссенции и сложность ─────────────────────────────────
def test_brew_with_excess_records_difficulty(app: AppService) -> None:
    """П-8.1: лишнее не мешает варке, но поднимает сложность и попадает в журнал."""
    app.inventory.set_reagent("krov-drakocherepakhi", 1)  # Вода×2, Огонь×1
    app.inventory.set_reagent("shcholkorekh", 1)  # Огонь×1

    outcome = app.brewing.brew(
        BrewRequest(
            base=BaseType.LIQUID,
            reagents={"krov-drakocherepakhi": 1, "shcholkorekh": 1},
            result_kind=ResultKind.KNOWN,
            potion_id="alkhimicheskiy-ogon",  # обычное, {fire: 2}
        )
    )
    entry = outcome.entry
    assert entry.portions == 1
    assert entry.excess.to_dict() == {"water": 2}
    assert entry.difficulty == 12  # 10 + 0 + 0 + 2
    assert app.inventory.potion_qty("alkhimicheskiy-ogon") == 1


def test_brew_two_portions_gives_two_potions(app: AppService) -> None:
    """П-8.2: на две порции хватило — и зелий выходит два."""
    app.inventory.set_reagent("shcholkorekh", 4)  # Огонь×1 ×4 = две порции {fire:2}

    outcome = app.brewing.brew(
        BrewRequest(
            base=BaseType.LIQUID,
            reagents={"shcholkorekh": 4},
            result_kind=ResultKind.KNOWN,
            potion_id="alkhimicheskiy-ogon",
            portions=2,
        )
    )
    assert outcome.entry.portions == 2
    assert outcome.entry.yield_qty == 2
    assert outcome.entry.difficulty == 12  # 10 + 0 + 2 + 0
    assert outcome.entry.excess.is_empty
    assert app.inventory.potion_qty("alkhimicheskiy-ogon") == 2
    assert app.inventory.reagent_qty("shcholkorekh") == 0


def test_brew_cannot_claim_more_portions_than_covered(app: AppService) -> None:
    """Просить больше порций, чем покрыто элементами, нельзя — счёт идёт по рецепту."""
    app.inventory.set_reagent("shcholkorekh", 2)
    outcome = app.brewing.brew(
        BrewRequest(
            base=BaseType.LIQUID,
            reagents={"shcholkorekh": 2},
            result_kind=ResultKind.KNOWN,
            potion_id="alkhimicheskiy-ogon",
            portions=5,
        )
    )
    assert outcome.entry.portions == 1
    assert app.inventory.potion_qty("alkhimicheskiy-ogon") == 1


def test_lab_candidates_sorted_by_difficulty(app: AppService) -> None:
    """Лаборатория показывает, что выйдет и во что обойдётся бросок (П-8)."""
    app.inventory.set_reagent("shcholkorekh", 2)
    app.inventory.set_reagent("svechnaya-roza", 1)

    hint = app.brewing.hint(BaseType.VISCOUS, {"shcholkorekh": 2, "svechnaya-roza": 1})
    names = [c.potion.name for c in hint.candidates]
    assert "Пламя Саламандры" in names  # вязкая, {fire:2, light:1} — ровно

    salamander = next(c for c in hint.candidates if c.potion.name == "Пламя Саламандры")
    assert salamander.portions == 1
    assert salamander.is_exact
    assert salamander.difficulty.total == 12  # необычное, без лишнего

    # Список идёт от простого броска к сложному.
    assert [c.difficulty.total for c in hint.candidates] == sorted(
        c.difficulty.total for c in hint.candidates
    )


def test_lab_candidate_with_excess(app: AppService) -> None:
    """П-8.1: Огонь×2 и лишняя Вода×2 — Алхимический Огонь сложнее на 2."""
    app.inventory.set_reagent("krov-drakocherepakhi", 1)
    app.inventory.set_reagent("shcholkorekh", 1)

    hint = app.brewing.hint(BaseType.LIQUID, {"krov-drakocherepakhi": 1, "shcholkorekh": 1})
    fire = next(c for c in hint.candidates if c.potion.id == "alkhimicheskiy-ogon")
    assert fire.excess.to_dict() == {"water": 2}
    assert fire.difficulty.total == 12
    assert not fire.is_exact


def test_can_brew_includes_excess_variants(app: AppService) -> None:
    """С П-8.1 из «неподходящих» реагентов теперь что-то да варится.

    Две Крови дракочерепахи — это Огонь×2 и Вода×4: рецепт Алхимического Огня
    покрыт, но четыре лишние единицы поднимают сложность с 10 до 14.
    """
    app.inventory.set_reagent("krov-drakocherepakhi", 2)

    assert app.brewing.can_brew(max_excess=0) == []
    assert app.brewing.can_brew(max_excess=2) == []  # четырёх лишних бюджет не даёт

    rows = {r.potion.id: r for r in app.brewing.can_brew(max_excess=4)}
    assert "alkhimicheskiy-ogon" in rows
    best = rows["alkhimicheskiy-ogon"].best
    assert best.combination.excess.to_dict() == {"water": 4}
    assert best.difficulty.total == 14


def test_max_portions_for(app: AppService) -> None:
    app.inventory.set_reagent("shcholkorekh", 5)
    assert app.brewing.max_portions_for("alkhimicheskiy-ogon") == 2
    assert app.brewing.max_portions_for("alkhimicheskiy-ogon", {"shcholkorekh": 2}) == 1


def test_journal_keeps_difficulty_after_restart(app: AppService, tmp_path) -> None:
    from alchimist.services import build_app

    app.inventory.set_reagent("shcholkorekh", 4)
    app.brewing.brew(
        BrewRequest(
            base=BaseType.LIQUID,
            reagents={"shcholkorekh": 4},
            result_kind=ResultKind.KNOWN,
            potion_id="alkhimicheskiy-ogon",
            portions=2,
        )
    )
    fresh = build_app(tmp_path)
    entry = fresh.journal.entries()[0]
    assert entry.portions == 2
    assert entry.difficulty == 12
