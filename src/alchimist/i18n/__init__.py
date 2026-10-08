"""Перевод строк и тексты по кодам (03 §8, NFR-6).

Ядро возвращает коды с параметрами, текст собирается здесь. Механизм — gettext,
он не зависит от Qt и переживёт смену интерфейса. Исходный язык строк — русский.
"""

from __future__ import annotations

import gettext as _gettext
import os
from pathlib import Path

from alchimist.core.errors import ErrorCode, Message, WarningCode

DOMAIN = "alchimist"
LOCALE_DIR = Path(__file__).parent / "locale"
DEFAULT_LANGUAGE = "ru"

#: Языки, для которых есть каталог (или которые и так исходные).
AVAILABLE_LANGUAGES: dict[str, str] = {"ru": "Русский", "en": "English"}

_translation: _gettext.NullTranslations = _gettext.NullTranslations()
_language = DEFAULT_LANGUAGE


def set_language(language: str | None = None) -> str:
    """Переключает язык. None — берётся из окружения, иначе русский."""
    global _translation, _language
    language = language or os.environ.get("ALCHIMIST_LANG") or DEFAULT_LANGUAGE
    _translation = _gettext.translation(
        DOMAIN, localedir=str(LOCALE_DIR), languages=[language], fallback=True
    )
    _language = language
    return language


def language() -> str:
    return _language


def _(text: str) -> str:
    """Перевод строки интерфейса."""
    return _translation.gettext(text)


def ngettext(singular: str, plural: str, n: int) -> str:
    return _translation.ngettext(singular, plural, n)


def plural_ru(n: int, one: str, few: str, many: str) -> str:
    """Русские формы числа: 1 зелье, 2 зелья, 5 зелий."""
    n = abs(n) % 100
    if 11 <= n <= 14:
        return many
    match n % 10:
        case 1:
            return one
        case 2 | 3 | 4:
            return few
        case _:
            return many


#: Шаблоны текстов по кодам. Параметры подставляются через `format`.
_TEMPLATES: dict[str, str] = {
    WarningCode.RARITY_UNITS_MISMATCH: (
        "«{name}»: единиц элементов {actual}, а по редкости должно быть {expected} (П-3.2)"
    ),
    WarningCode.RECIPE_SIZE_MISMATCH: (
        "«{name}»: в рецепте {actual} единиц, а по редкости должно быть {expected} (П-5.2)"
    ),
    WarningCode.RECIPE_COLLISION: (
        "«{name}»: такой рецепт {base_phrase} уже есть у {others_ru} (П-5.6)"
    ),
    WarningCode.RECIPE_NO_BASES: "«{name}»: в рецепте не выбрана ни одна основа",
    WarningCode.RECIPE_NO_ELEMENTS: "«{name}»: в рецепте не указано ни одного элемента",
    WarningCode.INGREDIENT_NO_ELEMENTS: "«{name}»: не указано ни одного элемента",
    WarningCode.STORAGE_RECOVERED_FROM_BAK: (
        "Файл {path} не читается, взята резервная копия {backup}"
    ),
    ErrorCode.DUPLICATE_NAME: "Название «{name}» уже занято",
    ErrorCode.EMPTY_NAME: "Название не может быть пустым",
    ErrorCode.INGREDIENT_IN_USE: (
        "«{name}» есть в инвентаре, журнале или нужен рецепту как основа, удалить нельзя — "
        "можно скрыть"
    ),
    ErrorCode.POTION_IN_USE: "«{name}» есть в инвентаре или журнале, удалить нельзя — можно скрыть",
    ErrorCode.NOT_FOUND: "Запись не найдена: {id}",
    ErrorCode.NOT_ENOUGH_REAGENTS: "В инвентаре не хватает реагентов: {name}",
    ErrorCode.NOT_ENOUGH_POTIONS: "В инвентаре нет такого зелья: {name}",
    ErrorCode.NO_BASE: "Без основы зелье сварить нельзя (П-4.3)",
    ErrorCode.NO_REAGENTS: "Не выбрано ни одного реагента",
    ErrorCode.TOO_MANY_REAGENTS: (
        "В экстракт помещается не больше {maximum} реагентов, а положено {actual} (П-9.1)"
    ),
    ErrorCode.DISTILL_NO_CHANGE: "Разбирать нечего: выйдет ровно то же, что и положили",
    ErrorCode.MISSING_ESSENCE: "В справочнике нет эссенции «{name}» — разбор записать некуда",
    ErrorCode.DISTILL_NO_EXTRACT: (
        "Разбирать не в чем: нужен флакон «{name}», а в сумке его нет (П-9.6)"
    ),
    ErrorCode.STORAGE_CORRUPT: "Файл {path} повреждён: {reason}",
    ErrorCode.STORAGE_UNKNOWN_SCHEMA: (
        "Файл {path} записан версией формата {version}, приложение понимает {supported}"
    ),
    ErrorCode.EXCHANGE_BAD_FORMAT: "Это не файл обмена справочником",
    ErrorCode.GM_ONLY: "Справочник может менять и выгружать только GM",
    ErrorCode.NAME_RESERVED: "Имя «{name}» зарезервировано, выберите другое",
    ErrorCode.NO_CHARACTER: "Сначала создайте персонажа",
    ErrorCode.LAST_CHARACTER: "Нельзя удалить единственного персонажа",
    ErrorCode.RECIPE_UNKNOWN: "Рецепт «{name}» пока не знает никто, изучать нечего",
    ErrorCode.NO_SPECIAL_BASE: "В сумке нет основы «{name}»",
}


def _decorate(params: dict) -> dict:
    """Добавляет к параметрам готовые к показу варианты: списки, названия основ."""
    from alchimist.core.models import BASE_NAMES_RU_LOC, BaseType

    decorated = dict(params)
    others = params.get("others")
    if isinstance(others, (list, tuple, set)):
        decorated["others_ru"] = ", ".join(f"«{o}»" for o in others)
    base = params.get("base")
    if base:
        try:
            decorated["base_ru"] = BASE_NAMES_RU_LOC[BaseType(base)]
            decorated["base_phrase"] = f"на {decorated['base_ru']} основе"
        except ValueError:
            # Особая основа (П-4.4): падежа у названия нет, поэтому «на основе «…»».
            special = params.get("base_name") or str(base)
            decorated["base_ru"] = special
            decorated["base_phrase"] = f"на основе «{special}»"
    for key, value in list(decorated.items()):
        if value is None:
            decorated[key] = "—"
    return decorated


def describe(message: Message) -> str:
    """Текст сообщения по коду и параметрам."""
    template = _TEMPLATES.get(message.code)
    if template is None:
        return f"{message.code}: {message.params}"
    try:
        return _(template).format(**_decorate(message.params))
    except (KeyError, IndexError):
        return f"{_(template)} {message.params}"


set_language()
