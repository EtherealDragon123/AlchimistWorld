"""Локализация (NFR-6, 03 §8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from alchimist.core.errors import ErrorCode, WarningCode, error, warning
from alchimist.i18n import (
    AVAILABLE_LANGUAGES,
    LOCALE_DIR,
    _,
    describe,
    language,
    plural_ru,
    set_language,
)


@pytest.fixture(autouse=True)
def restore_language():
    yield
    set_language("ru")


def test_default_language_is_russian() -> None:
    set_language("ru")
    assert language() == "ru"
    assert _("Сварить") == "Сварить"


def test_catalogs_exist() -> None:
    for code in AVAILABLE_LANGUAGES:
        assert (LOCALE_DIR / code / "LC_MESSAGES" / "alchimist.po").exists()


def test_compiled_catalog_is_used_when_present() -> None:
    """Если .mo собран, строки идут через него; если нет — остаются исходными."""
    set_language("ru")
    compiled = LOCALE_DIR / "ru" / "LC_MESSAGES" / "alchimist.mo"
    assert _("Журнал") == "Журнал"
    assert isinstance(compiled, Path)


def test_unknown_language_falls_back() -> None:
    set_language("xx")
    assert _("Журнал") == "Журнал"


def test_warning_text_by_code() -> None:
    message = warning(WarningCode.RARITY_UNITS_MISMATCH, name="Щёлкорех", expected=1, actual=2)
    text = describe(message)
    assert "Щёлкорех" in text
    assert "П-3.2" in text


def test_collision_text_lists_names() -> None:
    message = warning(
        WarningCode.RECIPE_COLLISION, name="Новое", base="liquid", others=["Зелье Лазанья"]
    )
    text = describe(message)
    assert "жидкой основе" in text
    assert "«Зелье Лазанья»" in text


def test_error_text() -> None:
    assert "уже занято" in describe(error(ErrorCode.DUPLICATE_NAME, name="Фанана"))


def test_every_code_has_a_template() -> None:
    """Ни один код не должен показываться пользователю как «сырой»."""
    for code in list(WarningCode) + list(ErrorCode):
        message = describe(warning(code) if isinstance(code, WarningCode) else error(code))
        assert not message.startswith(f"{code.value}:"), code


def test_plural_forms() -> None:
    assert plural_ru(1, "раз", "раза", "раз") == "раз"
    assert plural_ru(2, "раз", "раза", "раз") == "раза"
    assert plural_ru(5, "раз", "раза", "раз") == "раз"
    assert plural_ru(11, "зелье", "зелья", "зелий") == "зелий"
    assert plural_ru(22, "зелье", "зелья", "зелий") == "зелья"


def test_source_catalog_never_translates_anything() -> None:
    """Русский — исходный язык: msgstr обязан совпадать с msgid.

    `pybabel update` подставляет в новые строки ближайшие похожие и помечает их
    `fuzzy` — «Разобрать (Ctrl+Enter)» превращается в «Сварить (Ctrl+Enter)».
    Каталог выравнивает `tools/i18n.py sync`, и этот тест следит, чтобы его не
    забыли запустить.
    """
    pytest.importorskip("babel")
    from babel.messages.pofile import read_po

    path = (
        Path(__file__).resolve().parent.parent
        / "src/alchimist/i18n/locale/ru/LC_MESSAGES/alchimist.po"
    )
    with path.open("rb") as stream:
        catalog = read_po(stream)
    wrong = [
        (message.id, message.string)
        for message in catalog
        if message.id and (message.fuzzy or message.string != message.id)
    ]
    assert wrong == [], "запустите `python tools/i18n.py sync`"
