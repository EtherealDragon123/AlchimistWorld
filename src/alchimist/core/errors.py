"""Коды ошибок и предупреждений (03 §2).

Ядро не возвращает готовый текст: только код с параметрами. Текст по коду
собирает `alchimist.i18n`, которым пользуется любой интерфейс.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class WarningCode(StrEnum):
    """Предупреждения: сохранить можно, но что-то не сходится."""

    #: П-3.2: число единиц реагента ≠ его редкость.
    RARITY_UNITS_MISMATCH = "rarity_units_mismatch"
    #: П-5.2: число единиц рецепта ≠ редкость зелья + 1.
    RECIPE_SIZE_MISMATCH = "recipe_size_mismatch"
    #: П-5.6: ключ (основа, элементы) уже занят другим зельем.
    RECIPE_COLLISION = "recipe_collision"
    #: Рецепт без основ.
    RECIPE_NO_BASES = "recipe_no_bases"
    #: Рецепт без элементов.
    RECIPE_NO_ELEMENTS = "recipe_empty_elements"
    #: Реагент без элементов.
    INGREDIENT_NO_ELEMENTS = "ingredient_no_elements"
    #: Импорт: не разобрали рецепт, сырой текст ушёл в recipe_note.
    IMPORT_RECIPE_UNPARSED = "import_recipe_unparsed"
    #: Импорт: не узнали элемент.
    IMPORT_UNKNOWN_ELEMENT = "import_unknown_element"
    #: Импорт: не узнали редкость.
    IMPORT_UNKNOWN_RARITY = "import_unknown_rarity"
    #: Импорт: имя повторяется, id получил суффикс.
    IMPORT_DUPLICATE_NAME = "import_duplicate_name"
    #: Импорт: непонятная пометка в скобках.
    IMPORT_UNKNOWN_TAG = "import_unknown_tag"
    #: Импорт: применён синоним («Ветер» → Воздух, «Жидкость» → Жидкая).
    IMPORT_SYNONYM_APPLIED = "import_synonym_applied"
    #: Импорт: указатель «По реагентам» расходится с карточкой.
    IMPORT_INDEX_MISMATCH = "import_index_mismatch"
    #: Импорт: запись без блока элементов.
    IMPORT_NO_ELEMENTS = "import_no_elements"
    #: Хранилище: файл повреждён, взята резервная копия.
    STORAGE_RECOVERED_FROM_BAK = "storage_recovered_from_bak"


class ErrorCode(StrEnum):
    """Ошибки: операция не выполняется."""

    #: Название реагента или зелья уже занято (FR-1.4).
    DUPLICATE_NAME = "duplicate_name"
    #: Пустое название.
    EMPTY_NAME = "empty_name"
    #: Реагент используется в инвентаре или журнале (FR-1.5).
    INGREDIENT_IN_USE = "ingredient_in_use"
    #: Зелье используется в инвентаре или журнале.
    POTION_IN_USE = "potion_in_use"
    #: Не найдено по id.
    NOT_FOUND = "not_found"
    #: В инвентаре не хватает реагентов для варки.
    NOT_ENOUGH_REAGENTS = "not_enough_reagents"
    #: В инвентаре нет такого зелья.
    NOT_ENOUGH_POTIONS = "not_enough_potions"
    #: Варка без основы (П-4.3).
    NO_BASE = "no_base"
    #: Варка без реагентов.
    NO_REAGENTS = "no_reagents"
    #: В экстракт положили больше пяти реагентов (П-9.1).
    TOO_MANY_REAGENTS = "too_many_reagents"
    #: Разбор ничего не изменит: на выходе тот же набор эссенций (П-9.4, П-9.5).
    DISTILL_NO_CHANGE = "distill_no_change"
    #: В справочнике нет эссенции, которая должна получиться при разборе.
    MISSING_ESSENCE = "missing_essence"
    #: Дистилляция без флакона «Дистиллирующего Экстракта» (П-9.6).
    DISTILL_NO_EXTRACT = "distill_no_extract"
    #: Файл данных повреждён (NFR-8).
    STORAGE_CORRUPT = "storage_corrupt"
    #: Неизвестная версия схемы файла (NFR-4).
    STORAGE_UNKNOWN_SCHEMA = "storage_unknown_schema"
    #: Файл обмена не того формата (FR-10.3).
    EXCHANGE_BAD_FORMAT = "exchange_bad_format"


@dataclass(frozen=True, slots=True)
class Message:
    """Код с параметрами. Текст собирается в i18n, здесь его нет намеренно."""

    code: WarningCode | ErrorCode
    params: dict[str, Any] = field(default_factory=dict)
    severity: Severity = Severity.WARNING

    def __post_init__(self) -> None:
        if isinstance(self.code, ErrorCode) and self.severity is Severity.WARNING:
            object.__setattr__(self, "severity", Severity.ERROR)


def warning(code: WarningCode, **params: Any) -> Message:
    return Message(code, params, Severity.WARNING)


def error(code: ErrorCode, **params: Any) -> Message:
    return Message(code, params, Severity.ERROR)


class AlchimistError(Exception):
    """Ошибка предметной области: несёт код и параметры, а не готовый текст."""

    def __init__(self, code: ErrorCode, **params: Any) -> None:
        super().__init__(f"{code.value}: {params}")
        self.code = code
        self.params = params

    @property
    def message(self) -> Message:
        return Message(self.code, self.params, Severity.ERROR)


class StorageError(AlchimistError):
    """Проблема с файлом данных (NFR-8): в параметрах путь и, если есть, строка."""
