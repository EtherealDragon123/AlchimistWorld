from __future__ import annotations

from datetime import date, timedelta

from alchimist.core.models import BaseType, JournalEntryType, Outcome, ResultKind
from alchimist.services.app import AppService
from alchimist.services.brewing import BrewRequest
from alchimist.services.journal import JournalFilter


def _brew(app: AppService, **changes) -> None:
    app.inventory.add_reagent("shcholkorekh", 2)
    request = BrewRequest(
        base=BaseType.LIQUID,
        reagents={"shcholkorekh": 2},
        result_kind=ResultKind.KNOWN,
        potion_id="alkhimicheskiy-ogon",
    ).with_(**changes)
    app.brewing.brew(request)


def test_journal_is_chronological(app: AppService) -> None:
    _brew(app)
    _brew(app, note="вторая")
    entries = app.journal.entries()
    assert entries[0].note == "вторая"
    assert entries[0].ts >= entries[1].ts


def test_filter_by_type_and_outcome(app: AppService) -> None:
    _brew(app)
    _brew(app, outcome=Outcome.FAILURE, result_kind=ResultKind.NONE)
    app.brewing.use_potion("alkhimicheskiy-ogon")

    only_brews = app.journal.filtered(JournalFilter(types=frozenset({JournalEntryType.BREW})))
    assert len(only_brews) == 2

    failures = app.journal.filtered(JournalFilter(outcomes=frozenset({Outcome.FAILURE})))
    assert len(failures) == 1


def test_filter_by_potion_and_period(app: AppService) -> None:
    _brew(app)
    today = date.today()
    assert app.journal.filtered(JournalFilter(potion_id="alkhimicheskiy-ogon"))
    assert app.journal.filtered(JournalFilter(since=today, until=today))
    assert not app.journal.filtered(JournalFilter(since=today + timedelta(days=1)))


def test_search_by_combination(app: AppService) -> None:
    """FR-8.4: «пробовал ли я Огонь+Огонь на жидкой основе?»"""
    _brew(app)
    entry = app.journal.entries()[0]
    found = app.journal.filtered(JournalFilter(base=BaseType.LIQUID, elements=entry.elements))
    assert len(found) == 1
    assert not app.journal.filtered(JournalFilter(base=BaseType.EXPLOSIVE, elements=entry.elements))


def test_successful_experiments_can_become_recipes(app: AppService) -> None:
    _brew(app)
    _brew(app, outcome=Outcome.FAILURE, result_kind=ResultKind.NONE)
    candidates = app.journal.successful_experiments()
    assert len(candidates) == 1
    assert candidates[0].result.potion_id == "alkhimicheskiy-ogon"


def test_use_is_recorded(app: AppService) -> None:
    _brew(app)
    app.brewing.use_potion("alkhimicheskiy-ogon", 1, "в бою с троллем")
    entry = app.journal.entries()[0]
    assert entry.type is JournalEntryType.USE
    assert entry.note == "в бою с троллем"
