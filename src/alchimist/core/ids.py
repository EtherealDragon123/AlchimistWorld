"""Транслитерация и slug для идентификаторов (03 §6.9)."""

from __future__ import annotations

import re
from collections.abc import Container

#: Таблица транслитерации кириллицы. Порядок важен: сначала многобуквенные.
_TRANSLIT: dict[str, str] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}

_ALLOWED = re.compile(r"[^a-z0-9]+")


def transliterate(text: str) -> str:
    """Кириллица → латиница. Остальные символы остаются как есть."""
    return "".join(_TRANSLIT.get(ch, ch) for ch in text.casefold())


def slugify(text: str) -> str:
    """«Могильная Лоза» → «mogilnaya-loza». Пустой результат → «item»."""
    slug = _ALLOWED.sub("-", transliterate(text)).strip("-")
    return slug or "item"


def unique_id(name: str, taken: Container[str]) -> str:
    """Slug названия; при совпадении добавляется суффикс «-2», «-3», …"""
    base = slugify(name)
    if base not in taken:
        return base
    suffix = 2
    while f"{base}-{suffix}" in taken:
        suffix += 1
    return f"{base}-{suffix}"


def normalize_name(name: str) -> str:
    """Ключ для проверки уникальности названий: регистр и пробелы не важны."""
    return " ".join(name.casefold().replace("ё", "е").split())
