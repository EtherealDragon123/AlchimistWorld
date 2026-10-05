"""Шина событий на обычных Python-колбэках (03 §2).

Qt здесь нет намеренно: `ui_qt/bridge.py` превращает эти события в Qt-сигналы.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Event:
    """База для всех событий."""


@dataclass(frozen=True, slots=True)
class CatalogChanged(Event):
    """Справочник изменился: добавили, поправили или удалили запись."""

    ingredient_ids: tuple[str, ...] = ()
    potion_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class InventoryChanged(Event):
    """Инвентарь изменился."""

    ingredient_ids: tuple[str, ...] = ()
    potion_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class JournalChanged(Event):
    """В журнале появилась или поменялась запись."""

    entry_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class QueueChanged(Event):
    """Очередь варок изменилась: подбор надо пересчитать от нового остатка."""


@dataclass(frozen=True, slots=True)
class SettingsChanged(Event):
    """Поменялись настройки: наборы, язык, профиль."""


Listener = Callable[[Event], None]


@dataclass(slots=True)
class EventBus:
    """Подписка по типу события. Ошибка в одном слушателе не ломает остальных."""

    _listeners: dict[type[Event], list[Listener]] = field(default_factory=dict)

    def subscribe(self, event_type: type[Event], listener: Listener) -> Callable[[], None]:
        self._listeners.setdefault(event_type, []).append(listener)
        return lambda: self.unsubscribe(event_type, listener)

    def unsubscribe(self, event_type: type[Event], listener: Listener) -> None:
        listeners = self._listeners.get(event_type)
        if listeners and listener in listeners:
            listeners.remove(listener)

    def publish(self, event: Event) -> None:
        for event_type, listeners in self._listeners.items():
            if isinstance(event, event_type):
                for listener in list(listeners):
                    listener(event)

    def clear(self) -> None:
        self._listeners.clear()
