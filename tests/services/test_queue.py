"""Очередь варок: резерв реагентов и пересчёт подбора (FR-12.x)."""

from __future__ import annotations

import pytest

from alchimist.core.errors import AlchimistError, ErrorCode
from alchimist.core.models import BaseType, BrewQueue, QueueEntry, ReagentStack, ResultKind
from alchimist.services import build_app
from alchimist.services.app import AppService
from alchimist.services.brewing import BrewRequest


def names(app: AppService, **kwargs) -> set[str]:
    return {row.potion.id for row in app.brewing.can_brew(**kwargs)}


# ── чистая логика очереди ────────────────────────────────────────────────────
def test_feasible_walks_in_order() -> None:
    """Запись выше занимает реагенты раньше (ответ мастера на вопрос о порядке)."""
    entry = lambda i, q: QueueEntry(i, "p", BaseType.LIQUID, (ReagentStack("shch", q),))  # noqa: E731
    queue = BrewQueue((entry("a", 2), entry("b", 2), entry("c", 2)))
    assert queue.feasible({"shch": 5}) == [True, True, False]
    assert queue.reserved({"shch": 5}) == {"shch": 4}
    assert queue.available({"shch": 5}) == {"shch": 1}


def test_infeasible_entry_reserves_nothing() -> None:
    """Запись, которую всё равно не сварить, чужие реагенты не занимает."""
    queue = BrewQueue(
        (
            QueueEntry("a", "p", BaseType.LIQUID, (ReagentStack("shch", 9),)),
            QueueEntry("b", "p", BaseType.LIQUID, (ReagentStack("shch", 1),)),
        )
    )
    assert queue.feasible({"shch": 2}) == [False, True]
    assert queue.reserved({"shch": 2}) == {"shch": 1}


def test_inactive_queue_reserves_nothing() -> None:
    queue = BrewQueue(
        (QueueEntry("a", "p", BaseType.LIQUID, (ReagentStack("shch", 2),)),), active=False
    )
    assert queue.reserved({"shch": 5}) == {}
    assert queue.available({"shch": 5}) == {"shch": 5}


# ── влияние на подбор ────────────────────────────────────────────────────────
def test_queue_recalculates_can_brew(app: AppService) -> None:
    """Главное требование: отложил одно — видно, что на другое уже не хватает."""
    app.inventory.set_reagent("shcholkorekh", 2)  # Огонь×1
    app.inventory.set_reagent("svechnaya-roza", 1)  # Свет×1

    assert "alkhimicheskiy-ogon" in names(app, max_excess=0)
    assert "plamya-salamandry" in names(app, max_excess=0)

    row = next(
        r for r in app.brewing.can_brew(max_excess=0) if r.potion.id == "alkhimicheskiy-ogon"
    )
    option = row.best
    app.queue.add(option.potion.id, option.base, option.combination.as_map(), option.portions)

    # Щёлкорехи заняты: не осталось ни на сам Огонь, ни на Пламя Саламандры.
    assert names(app, max_excess=0) == set()
    assert app.brewing.reserved_quantities() == {"shcholkorekh": 2}
    assert app.brewing.available_quantities() == {"svechnaya-roza": 1}


def test_queue_can_be_switched_off(app: AppService) -> None:
    app.inventory.set_reagent("shcholkorekh", 2)
    app.queue.add("alkhimicheskiy-ogon", BaseType.LIQUID, {"shcholkorekh": 2})
    assert names(app, max_excess=0) == set()

    app.queue.set_active(False)
    assert "alkhimicheskiy-ogon" in names(app, max_excess=0)
    assert app.brewing.reserved_quantities() == {}

    app.queue.set_active(True)
    assert names(app, max_excess=0) == set()


def test_queue_affects_almost_ready(app: AppService) -> None:
    """Ответ мастера: «Почти готово» тоже считается от остатка."""
    app.inventory.set_reagent("shcholkorekh", 2)
    app.inventory.set_reagent("svechnaya-roza", 1)

    before = {row.potion.id: row.missing.to_dict() for row in app.brewing.almost()}
    assert "plamya-salamandry" not in before  # пока варится, тут его нет

    app.queue.add("alkhimicheskiy-ogon", BaseType.LIQUID, {"shcholkorekh": 2})
    after = {row.potion.id: row.missing.to_dict() for row in app.brewing.almost()}
    assert after["plamya-salamandry"] == {"fire": 2}  # Щёлкорехи ушли в очередь


# ── жизненный цикл записи ────────────────────────────────────────────────────
def test_brewing_removes_the_entry(app: AppService) -> None:
    """Ответ мастера: сварили — запись уходит из очереди."""
    app.inventory.set_reagent("shcholkorekh", 2)
    app.queue.add("alkhimicheskiy-ogon", BaseType.LIQUID, {"shcholkorekh": 2})
    assert len(app.queue.entries) == 1

    app.brewing.brew(
        BrewRequest(
            base=BaseType.LIQUID,
            reagents={"shcholkorekh": 2},
            result_kind=ResultKind.KNOWN,
            potion_id="alkhimicheskiy-ogon",
        )
    )
    assert app.queue.entries == ()
    assert app.inventory.reagent_qty("shcholkorekh") == 0


def test_brewing_removes_the_matching_variant(app: AppService) -> None:
    """Из двух записей на одно зелье уходит та, чьими реагентами варили."""
    app.inventory.set_reagent("shcholkorekh", 2)
    app.inventory.set_reagent("tusklaya-essentsiya-ognya", 1)
    app.queue.add("alkhimicheskiy-ogon", BaseType.LIQUID, {"tusklaya-essentsiya-ognya": 1})
    app.queue.add("alkhimicheskiy-ogon", BaseType.LIQUID, {"shcholkorekh": 2})

    app.brewing.brew(
        BrewRequest(
            base=BaseType.LIQUID,
            reagents={"shcholkorekh": 2},
            result_kind=ResultKind.KNOWN,
            potion_id="alkhimicheskiy-ogon",
        )
    )
    left = app.queue.entries
    assert len(left) == 1
    assert left[0].reagent_map() == {"tusklaya-essentsiya-ognya": 1}


def test_brewing_something_else_leaves_queue_alone(app: AppService) -> None:
    app.inventory.set_reagent("shcholkorekh", 2)
    app.inventory.set_reagent("tkanevyy-list", 2)
    app.queue.add("alkhimicheskiy-ogon", BaseType.LIQUID, {"shcholkorekh": 2})

    app.brewing.brew(
        BrewRequest(
            base=BaseType.LIQUID,
            reagents={"tkanevyy-list": 2},
            result_kind=ResultKind.KNOWN,
            potion_id="zele-lazanya",
        )
    )
    assert len(app.queue.entries) == 1


# ── порядок и правка ─────────────────────────────────────────────────────────
def test_move_changes_who_gets_the_reagents(app: AppService) -> None:
    app.inventory.set_reagent("shcholkorekh", 2)
    first = app.queue.add("alkhimicheskiy-ogon", BaseType.LIQUID, {"shcholkorekh": 2})
    second = app.queue.add("alkhimicheskiy-ogon", BaseType.VISCOUS, {"shcholkorekh": 2})

    rows = app.queue.rows(
        app.inventory.reagent_quantities(), app.catalog.potion_map(), app.catalog.ingredient_map()
    )
    assert [r.feasible for r in rows] == [True, False]
    assert rows[0].entry.id == first.id

    app.queue.move(second.id, -1)
    rows = app.queue.rows(
        app.inventory.reagent_quantities(), app.catalog.potion_map(), app.catalog.ingredient_map()
    )
    assert rows[0].entry.id == second.id
    assert [r.feasible for r in rows] == [True, False]


def test_rows_report_what_is_missing(app: AppService) -> None:
    app.inventory.set_reagent("shcholkorekh", 1)
    app.queue.add("alkhimicheskiy-ogon", BaseType.LIQUID, {"shcholkorekh": 2})
    row = app.queue.rows(
        app.inventory.reagent_quantities(), app.catalog.potion_map(), app.catalog.ingredient_map()
    )[0]
    assert not row.feasible
    assert row.missing == {"shcholkorekh": 1}


def test_rows_carry_difficulty(app: AppService) -> None:
    """У записи видна сложность будущего броска (П-8)."""
    app.inventory.set_reagent("shcholkorekh", 4)
    app.queue.add("alkhimicheskiy-ogon", BaseType.LIQUID, {"shcholkorekh": 4}, portions=2)
    row = app.queue.rows(
        app.inventory.reagent_quantities(), app.catalog.potion_map(), app.catalog.ingredient_map()
    )[0]
    assert row.portions == 2
    assert row.difficulty.total == 12  # 10 + 0 + 2 + 0


def test_empty_entry_is_refused(app: AppService) -> None:
    with pytest.raises(AlchimistError) as excinfo:
        app.queue.add("alkhimicheskiy-ogon", BaseType.LIQUID, {})
    assert excinfo.value.code is ErrorCode.NO_REAGENTS


def test_queue_survives_restart(app: AppService, tmp_path) -> None:
    app.inventory.set_reagent("shcholkorekh", 2)
    app.queue.add("alkhimicheskiy-ogon", BaseType.VISCOUS, {"shcholkorekh": 2}, portions=1)
    app.queue.set_active(False)

    fresh = build_app(tmp_path)
    assert len(fresh.queue.entries) == 1
    assert fresh.queue.entries[0].base is BaseType.VISCOUS
    assert fresh.queue.is_active is False
