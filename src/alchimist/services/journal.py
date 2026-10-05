"""Журнал варок и использований (FR-8.x, П-7.4)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime

from alchimist.core.elements import ElementVector
from alchimist.core.errors import AlchimistError, ErrorCode, Message
from alchimist.core.models import (
    BaseType,
    JournalEntry,
    JournalEntryType,
    Outcome,
    ResultKind,
)
from alchimist.services.events import EventBus, JournalChanged
from alchimist.storage.repository import JournalRepository


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now() -> datetime:
    return datetime.now().astimezone()


@dataclass(frozen=True, slots=True)
class JournalFilter:
    """Фильтры экрана «Журнал» (FR-8.2)."""

    types: frozenset[JournalEntryType] | None = None
    outcomes: frozenset[Outcome] | None = None
    potion_id: str | None = None
    since: date | None = None
    until: date | None = None
    base: BaseType | None = None
    elements: ElementVector | None = None
    text: str = ""

    def matches(self, entry: JournalEntry, potion_name: str = "") -> bool:
        if self.types is not None and entry.type not in self.types:
            return False
        if self.outcomes is not None and (
            entry.outcome is None or entry.outcome not in self.outcomes
        ):
            return False
        if self.potion_id:
            ids = {entry.potion_id}
            if entry.result:
                ids.add(entry.result.potion_id)
            if self.potion_id not in ids:
                return False
        if self.since and entry.ts.date() < self.since:
            return False
        if self.until and entry.ts.date() > self.until:
            return False
        if self.base and entry.base != self.base:
            return False
        if self.elements is not None and entry.elements != self.elements:
            return False
        if self.text:
            needle = self.text.casefold()
            haystack = f"{entry.note} {potion_name}".casefold()
            if needle not in haystack:
                return False
        return True


@dataclass(slots=True)
class JournalService:
    repo: JournalRepository
    bus: EventBus
    _entries: list[JournalEntry] = field(default_factory=list)
    _notices: list[Message] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        self._entries = self.repo.load()
        self._notices = list(getattr(self.repo, "notices", []) or [])

    @property
    def notices(self) -> list[Message]:
        return list(self._notices)

    # ── чтение ────────────────────────────────────────────────────────────
    def entries(self, newest_first: bool = True) -> list[JournalEntry]:
        return sorted(self._entries, key=lambda e: e.ts, reverse=newest_first)

    def filtered(
        self, criteria: JournalFilter, names: dict[str, str] | None = None
    ) -> list[JournalEntry]:
        names = names or {}
        return [
            entry
            for entry in self.entries()
            if criteria.matches(entry, names.get(entry.potion_id or "", ""))
        ]

    def entry(self, entry_id: str) -> JournalEntry:
        found = next((e for e in self._entries if e.id == entry_id), None)
        if found is None:
            raise AlchimistError(ErrorCode.NOT_FOUND, id=entry_id)
        return found

    def combination_history(self, base: BaseType, elements: ElementVector) -> list[JournalEntry]:
        """«Эту комбинацию уже пробовали» (П-7.6, FR-7.4)."""
        key = (base, elements)
        return [
            entry for entry in self.entries() if not entry.undone and entry.combination_key == key
        ]

    def uses_ingredient(self, ingredient_id: str) -> bool:
        return any(
            r.ingredient_id == ingredient_id for entry in self._entries for r in entry.reagents
        )

    def uses_potion(self, potion_id: str) -> bool:
        return any(
            entry.potion_id == potion_id
            or (entry.result is not None and entry.result.potion_id == potion_id)
            for entry in self._entries
        )

    # ── запись ────────────────────────────────────────────────────────────
    def _persist(self, entries: Iterable[JournalEntry], changed: tuple[str, ...]) -> None:
        self._entries = list(entries)
        self.repo.save(self._entries)
        self.bus.publish(JournalChanged(changed))

    def prepare_write(self, entries: list[JournalEntry]):
        """Готовит `.tmp` без подмены: варка меняет два файла разом (03 §6.2)."""
        return self.repo.prepare(entries)  # type: ignore[attr-defined]

    def adopt(self, entries: list[JournalEntry]) -> None:
        """Принимает уже записанный на диск журнал, не трогая файлы."""
        self._entries = list(entries)

    def append(self, entry: JournalEntry) -> JournalEntry:
        self._persist([*self._entries, entry], (entry.id,))
        return entry

    def replace(self, entry: JournalEntry) -> JournalEntry:
        entries = [entry if e.id == entry.id else e for e in self._entries]
        self._persist(entries, (entry.id,))
        return entry

    def record_use(self, potion_id: str, qty: int = 1, note: str = "") -> JournalEntry:
        """Использование зелья (FR-4.2)."""
        return self.append(
            JournalEntry(
                id=new_id(),
                ts=now(),
                type=JournalEntryType.USE,
                potion_id=potion_id,
                qty=qty,
                note=note,
            )
        )

    def record_adjust(self, note: str, reagents=(), potion_id: str | None = None, qty: int = 0):
        """Ручное изменение инвентаря (FR-8.1, опционально)."""
        return self.append(
            JournalEntry(
                id=new_id(),
                ts=now(),
                type=JournalEntryType.ADJUST,
                reagents=tuple(reagents),
                potion_id=potion_id,
                qty=qty,
                note=note,
            )
        )

    def successful_experiments(self) -> list[JournalEntry]:
        """Записи, из которых можно сделать рецепт (FR-8.3, П-7.5)."""
        return [
            entry
            for entry in self.entries()
            if entry.type is JournalEntryType.BREW
            and not entry.undone
            and entry.outcome is Outcome.SUCCESS
            and entry.result is not None
            and entry.result.kind in (ResultKind.KNOWN, ResultKind.NEW)
            and entry.result.potion_id
            and entry.base is not None
            and not entry.elements.is_empty
        ]
