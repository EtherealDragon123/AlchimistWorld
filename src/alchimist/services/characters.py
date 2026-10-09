"""Персонажи: несколько на одну установку, у каждого свой профиль (FR-14.x).

Справочник общий, а наборы, инвентарь, журнал, очередь, изученные рецепты и
реагенты у каждого персонажа свои. GM — встроенный скрытый персонаж: появляется,
когда при создании персонажа ввели его имя, знает всё и один может менять справочник.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from alchimist.core.errors import AlchimistError, ErrorCode, Message
from alchimist.core.ids import normalize_name, unique_id
from alchimist.core.models import (
    GM_ID,
    GM_NAME,
    Character,
    Kit,
    Role,
    is_gm_name,
    is_starter_ingredient,
    starter_recipes,
)
from alchimist.services.catalog import CatalogService
from alchimist.services.events import CharacterChanged, EventBus
from alchimist.storage.character_store import CharacterStore
from alchimist.storage.settings_store import Settings


@dataclass(slots=True)
class CharacterService:
    store: CharacterStore
    catalog: CatalogService
    bus: EventBus
    _characters: dict[str, Character] = field(default_factory=dict)
    _active_id: str | None = None

    def __post_init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        self._characters = {}
        for character in self.store.load_all():
            if character.known_ingredients is None:
                character = self._know_all_ingredients(character)
            self._characters[character.id] = character
        if self._active_id not in self._characters:
            self._active_id = None

    def _know_all_ingredients(self, character: Character) -> Character:
        """Персонаж из версии до 2.5 знает все реагенты справочника (03 §6.11).

        Тогда реагенты не изучали — их знали все, и отнимать уже открытое при
        обновлении нечестно. Файл переписывается сразу, чтобы решение не зависело
        от того, что окажется в справочнике в следующий раз.
        """
        known = frozenset() if character.is_gm else self._all_ingredient_ids()
        character = character.with_(known_ingredients=known)
        self.store.save(character)
        return character

    def _all_ingredient_ids(self) -> frozenset[str]:
        return frozenset(i.id for i in self.catalog.catalog.ingredients)

    @property
    def notices(self) -> list[Message]:
        return list(self.store.notices)

    # ── чтение ────────────────────────────────────────────────────────────
    def characters(self) -> list[Character]:
        """Игроки по алфавиту, GM — в конце списка."""
        return sorted(self._characters.values(), key=lambda c: (c.is_gm, c.name.casefold()))

    @property
    def has_characters(self) -> bool:
        return bool(self._characters)

    @property
    def active(self) -> Character | None:
        return self._characters.get(self._active_id) if self._active_id else None

    def get(self, character_id: str) -> Character:
        character = self._characters.get(character_id)
        if character is None:
            raise AlchimistError(ErrorCode.NOT_FOUND, id=character_id)
        return character

    @property
    def kits(self) -> tuple[Kit, ...]:
        active = self.active
        return active.kits if active else (Kit.ALCHEMIST,)

    def known_recipe_ids(self) -> frozenset[str] | None:
        """Что знает активный персонаж. None — всё: это GM или персонажа нет вовсе.

        Без персонажа приложение ведёт себя как до их появления: так работают
        консоль на пустой папке данных и тесты сервисов.
        """
        active = self.active
        if active is None or active.is_gm:
            return None
        return active.known_recipes

    def known_ingredient_ids(self) -> frozenset[str] | None:
        """Изученные активным персонажем реагенты сверх стартовых. None — знает всё.

        Стартовые (обычные и эссенции) сюда не входят: их знают все, проверка —
        `Character.knows_ingredient` или `CatalogService.knows_ingredient`.
        """
        active = self.active
        if active is None or active.is_gm or active.known_ingredients is None:
            return None
        return active.known_ingredients

    def can_edit_catalog(self) -> bool:
        """FR-14.6: справочник меняет только GM (или когда персонажей нет вовсе)."""
        active = self.active
        return active is None or active.is_gm

    # ── выбор ─────────────────────────────────────────────────────────────
    def resolve_active(self, preferred: str | None) -> str | None:
        """Кого открыть: того, с кем закрылись, иначе первого по списку."""
        if preferred and preferred in self._characters:
            return preferred
        ordered = self.characters()
        return ordered[0].id if ordered else None

    def activate(self, character_id: str | None) -> None:
        """Только запоминает выбор: профиль переключает `AppService.switch_character`."""
        if character_id is not None:
            self.get(character_id)
        self._active_id = character_id

    # ── создание и правка ─────────────────────────────────────────────────
    def create(
        self, name: str, kits: Iterable[Kit] = (), *, known: Iterable[str] | None = None
    ) -> Character:
        """Новый персонаж. Имя GM вместо игрока добавляет встроенного GM (FR-14.6).

        Игрок с самого начала знает рецепты всех обычных зелий из справочника
        (FR-14.2), остальные изучает сам. `known` задаёт это явно — так переносится
        персонаж из старой версии, где все рецепты справочника были известны всем.
        """
        name = name.strip()
        if not name:
            raise AlchimistError(ErrorCode.EMPTY_NAME)
        if is_gm_name(name):
            existing = self._characters.get(GM_ID)
            if existing is not None:
                return existing
            character = Character(GM_ID, GM_NAME, Role.GM, tuple(kits))
        else:
            self._check_name(name)
            learned = (
                starter_recipes(self.catalog.catalog.potions) if known is None else frozenset(known)
            )
            character_id = unique_id(name, self.store.taken_ids())
            character = Character(character_id, name, Role.PLAYER, tuple(kits), learned)
        self.store.save(character)
        self._characters[character.id] = character
        return character

    def rename(self, character_id: str, name: str) -> Character:
        character = self.get(character_id)
        name = name.strip()
        if not name:
            raise AlchimistError(ErrorCode.EMPTY_NAME)
        if character.is_gm:
            # У GM имя фиксированное: по нему его и добавляют.
            raise AlchimistError(ErrorCode.NAME_RESERVED, name=GM_NAME)
        self._check_name(name, except_id=character_id)
        return self._save(character.with_(name=name))

    def delete(self, character_id: str) -> None:
        """Удаляет персонажа вместе с профилем. Активного переключает `AppService`."""
        self.get(character_id)
        if len(self._characters) <= 1:
            raise AlchimistError(ErrorCode.LAST_CHARACTER)
        self.store.delete(character_id)
        del self._characters[character_id]
        if self._active_id == character_id:
            self._active_id = None

    def _check_name(self, name: str, *, except_id: str | None = None) -> None:
        if is_gm_name(name):
            raise AlchimistError(ErrorCode.NAME_RESERVED, name=name)
        wanted = normalize_name(name)
        for other in self._characters.values():
            if other.id != except_id and normalize_name(other.name) == wanted:
                raise AlchimistError(ErrorCode.DUPLICATE_NAME, name=name)

    # ── настройки активного персонажа ─────────────────────────────────────
    def _require_active(self) -> Character:
        active = self.active
        if active is None:
            raise AlchimistError(ErrorCode.NO_CHARACTER)
        return active

    def _save(self, character: Character) -> Character:
        self.store.save(character)
        self._characters[character.id] = character
        self.bus.publish(CharacterChanged())
        return character

    def set_kits(self, kits: Iterable[Kit]) -> Character:
        """FR-9.1: можно выбрать несколько наборов, пустой список — алхимик."""
        return self._save(self._require_active().with_(kits=tuple(kits)))

    def set_show_unknown(self, show: bool) -> Character:
        """FR-14.4: показывать ли в справочнике неизученные рецепты."""
        return self._save(self._require_active().with_(show_unknown=bool(show)))

    def learn(self, potion_id: str) -> Character:
        """FR-14.3: изучить рецепт. Изучить можно только то, что есть в справочнике."""
        active = self._require_active()
        potion = self.catalog.raw_potion(potion_id)
        if potion.recipe is None:
            raise AlchimistError(ErrorCode.RECIPE_UNKNOWN, name=potion.name, id=potion.id)
        if active.knows(potion_id):
            return active
        return self._save(active.with_(known_recipes=active.known_recipes | {potion_id}))

    def forget(self, potion_id: str) -> Character:
        active = self._require_active()
        if active.is_gm or potion_id not in active.known_recipes:
            return active
        return self._save(active.with_(known_recipes=active.known_recipes - {potion_id}))

    # ── изучение реагентов (FR-14.9) ──────────────────────────────────────
    def learn_ingredients(self, ingredient_ids: Iterable[str]) -> Character | None:
        """Изучить реагенты пачкой — одна запись в файл. Стартовые не записываются.

        Без персонажа (консоль на пустой папке, тесты сервисов) знать нечего: там
        и так известно всё.
        """
        active = self.active
        if active is None:
            return None
        new = set()
        for ingredient_id in ingredient_ids:
            ingredient = self.catalog.catalog.ingredient_by_id(ingredient_id)
            if ingredient is None:
                raise AlchimistError(ErrorCode.NOT_FOUND, id=ingredient_id)
            if not active.knows_ingredient(ingredient):
                new.add(ingredient_id)
        if not new:
            return active
        return self._save(active.with_(known_ingredients=active.known_ingredients | new))

    def learn_ingredient(self, ingredient_id: str) -> Character:
        self._require_active()
        return self.learn_ingredients([ingredient_id])  # type: ignore[return-value]

    def forget_ingredient(self, ingredient_id: str) -> Character:
        """Забыть изученный реагент. Стартовые и у GM не забываются.

        Лежит ли реагент в сумке, проверяет `AppService`: инвентаря тут не видно.
        """
        active = self._require_active()
        ingredient = self.catalog.catalog.ingredient_by_id(ingredient_id)
        if ingredient is None:
            raise AlchimistError(ErrorCode.NOT_FOUND, id=ingredient_id)
        known = active.known_ingredients
        if active.is_gm or is_starter_ingredient(ingredient) or not known:
            return active
        if ingredient_id not in known:
            return active
        return self._save(active.with_(known_ingredients=known - {ingredient_id}))

    # ── перенос со старых версий (03 §6.12) ───────────────────────────────
    def migrate_legacy(self, settings: Settings) -> list[Character]:
        """Профили, где играли до появления персонажей, становятся персонажами.

        Имя и наборы берутся из старого `settings.toml`. Знает такой персонаж все
        рецепты и реагенты справочника: раньше всё записанное было известно всем, и
        отнимать уже открытое при обновлении было бы нечестно.
        """
        migrated: list[Character] = []
        legacy_name = settings.legacy_character_name.strip()
        for profile in self.store.legacy_ids():
            name = legacy_name if profile == settings.active_profile and legacy_name else profile
            if is_gm_name(name) or any(
                normalize_name(c.name) == normalize_name(name) for c in self._characters.values()
            ):
                name = profile
            character = Character(
                profile,
                name,
                Role.PLAYER,
                settings.legacy_kits,
                self.catalog.recipe_ids(),
                known_ingredients=self._all_ingredient_ids(),
            )
            self.store.save(character)
            self._characters[character.id] = character
            migrated.append(character)
        return migrated
