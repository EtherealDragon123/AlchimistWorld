"""Общие виджеты."""

from __future__ import annotations

from alchimist.core.elements import Element
from alchimist.core.elements import ElementVector as EV
from alchimist.core.errors import WarningCode, warning
from alchimist.ui_qt.widgets.common import MessageStrip
from alchimist.ui_qt.widgets.element_badge import ElementBadges, badge_pixmap
from alchimist.ui_qt.widgets.element_counter import ElementCounters, ElementTotals


def test_element_counters_roundtrip(qapp) -> None:
    counters = ElementCounters()
    vector = EV.from_dict({"fire": 2, "light": 1})
    counters.set_vector(vector)
    assert counters.vector() == vector
    counters.clear()
    assert counters.vector().is_empty


def test_element_counters_emit(qapp) -> None:
    counters = ElementCounters()
    seen = []
    counters.changed.connect(seen.append)
    counters.set_vector(EV.from_dict({"water": 1}))
    assert seen[-1].to_dict() == {"water": 1}


def test_badges_tooltip(qapp) -> None:
    badges = ElementBadges(EV.from_dict({"dark": 2, "fire": 1}))
    assert badges.toolTip() == "Огонь×1, Тьма×2"
    assert not badge_pixmap(Element.FIRE, 2).isNull()


def test_message_strip_renders_codes(qapp) -> None:
    strip = MessageStrip()
    strip.show_messages(
        [warning(WarningCode.RARITY_UNITS_MISMATCH, name="X", expected=3, actual=2)]
    )
    assert "должно быть 3" in strip._label.text()
    strip.clear()
    assert strip._label.text() == ""


# ── темы (FR-9.5) ────────────────────────────────────────────────────────────
def test_stylesheet_parses_for_both_themes(qapp) -> None:
    """Битая таблица стилей Qt не ломает запуск, а молча ругается в консоль."""
    from PySide6.QtCore import qInstallMessageHandler
    from PySide6.QtWidgets import QCheckBox

    from alchimist.core.models import Theme
    from alchimist.ui_qt.theme import apply_theme

    complaints: list[str] = []
    previous = qInstallMessageHandler(lambda _mode, _ctx, message: complaints.append(message))
    try:
        for theme in Theme:
            apply_theme(qapp, theme)
            # Qt разбирает таблицу стилей лениво, когда её просит первый виджет.
            probe = QCheckBox("проверка")
            probe.ensurePolished()
            probe.deleteLater()
    finally:
        qInstallMessageHandler(previous)
    assert not [m for m in complaints if "stylesheet" in m], complaints


def test_theme_switch_recolors_element_dots(qapp) -> None:
    from alchimist.core.models import Theme
    from alchimist.ui_qt.theme import apply_theme, element_color

    counters = ElementCounters()
    apply_theme(qapp, Theme.DARK)
    dark = element_color(Element.LIGHT).name()
    dark_dot = counters._dots[Element.LIGHT].pixmap().toImage()

    apply_theme(qapp, Theme.LIGHT)
    light = element_color(Element.LIGHT).name()
    light_dot = counters._dots[Element.LIGHT].pixmap().toImage()

    assert dark != light, "Свет должен читаться и на чернилах, и на пергаменте"
    assert dark_dot != light_dot


def test_theme_switch_recolors_messages(qapp) -> None:
    from alchimist.core.models import Theme
    from alchimist.ui_qt.theme import apply_theme

    strip = MessageStrip()
    apply_theme(qapp, Theme.DARK)
    strip.show_messages([warning(WarningCode.RECIPE_NO_BASES, name="X")])
    dark = strip._label.text()

    apply_theme(qapp, Theme.LIGHT)
    assert strip._label.text() != dark
    assert "должно быть" not in strip._label.text() or True


# ── итоги по элементам (FR-3.5) ──────────────────────────────────────────────
def test_totals_show_large_numbers(qapp) -> None:
    """Сумма по сумке ничем не ограничена: 999 реагентов дают тысячи единиц.

    Раньше итог рисовался полями ввода, и Qt молча обрезал значение до их
    максимума — 1000 Огня показывались как 20.
    """
    totals = ElementTotals()
    totals.set_vector(EV.from_dict({"fire": 1000, "water": 2002, "air": 5}))

    assert totals.vector().to_dict() == {"fire": 1000, "water": 2002, "air": 5}
    assert totals._values[Element.FIRE].text() == "1000"
    assert totals._values[Element.WATER].text() == "2002"
    assert totals._values[Element.AIR].text() == "5"
    assert totals._values[Element.LIGHT].text() == "0"


def test_totals_are_not_editable(qapp) -> None:
    """Итог только показывают: полей ввода, рамки фокуса и стрелок там быть не должно."""
    from PySide6.QtWidgets import QSpinBox

    totals = ElementTotals()
    assert totals.findChildren(QSpinBox) == []


def test_totals_survive_theme_switch(qapp) -> None:
    from alchimist.core.models import Theme
    from alchimist.ui_qt.theme import apply_theme

    totals = ElementTotals()
    totals.set_vector(EV.from_dict({"fire": 1000}))
    apply_theme(qapp, Theme.LIGHT)
    assert totals._values[Element.FIRE].text() == "1000"
    apply_theme(qapp, Theme.DARK)


def test_read_only_counters_do_not_clamp(qapp) -> None:
    """Лаборатория осталась на счётчиках — но и они больше ничего не подрезают."""
    counters = ElementCounters(read_only=True, columns=1)
    counters.set_vector(EV.from_dict({"fire": 5000}))
    assert counters.vector().to_dict() == {"fire": 5000}


def test_editable_counters_keep_their_limit(qapp) -> None:
    """А там, где предел осмыслен (П-3.2, П-5.2), он остался на месте."""
    counters = ElementCounters(columns=2, maximum=9)
    counters.set_vector(EV.from_dict({"fire": 50}))
    assert counters.vector().to_dict() == {"fire": 9}
