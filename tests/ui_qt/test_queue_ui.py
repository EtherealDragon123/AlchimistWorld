"""Очередь в интерфейсе: панель в «Могу сварить» и её влияние (FR-12.x)."""

from __future__ import annotations

import pytest

from alchimist.core.models import BaseType
from alchimist.ui_qt.pages.can_brew import ROLE_OPTION, CanBrewPage
from alchimist.ui_qt.pages.lab import LabPage
from alchimist.ui_qt.pages.reagents import ReagentsPage


def _page(window, kind):
    page = next(p for p in window.pages if isinstance(p, kind))
    window.go_to(kind)
    return page


def _names(tree) -> set[str]:
    return {tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())}


def test_enqueue_recalculates_the_list(window, ui_app) -> None:
    """Главное: отложил вариант — список выше пересчитался от остатка."""
    ui_app.inventory.set_reagent("shcholkorekh", 2)
    ui_app.inventory.set_reagent("svechnaya-roza", 1)
    page = _page(window, CanBrewPage)
    page.max_excess.setValue(0)

    assert {"Алхимический Огонь", "Пламя Саламандры"} <= _names(page.tree)
    assert page.queue_empty.isVisible()

    top = next(
        page.tree.topLevelItem(i)
        for i in range(page.tree.topLevelItemCount())
        if page.tree.topLevelItem(i).text(0) == "Алхимический Огонь"
    )
    option = top.child(0).data(0, ROLE_OPTION)
    page._enqueue(option)

    # Реагенты заняты — в списке не осталось ничего.
    assert _names(page.tree) == set()
    assert page.empty.isVisible()
    # А в очереди появилась запись.
    assert page.queue_tree.topLevelItemCount() == 1
    assert page.queue_tree.topLevelItem(0).text(0) == "Алхимический Огонь"
    assert page.queue_tree.topLevelItem(0).text(4) == "отложено"
    assert "занято реагентов: 2" in page.queue_summary.text()


def test_queue_toggle(window, ui_app) -> None:
    ui_app.inventory.set_reagent("shcholkorekh", 2)
    ui_app.queue.add("alkhimicheskiy-ogon", BaseType.LIQUID, {"shcholkorekh": 2})
    page = _page(window, CanBrewPage)
    page.max_excess.setValue(0)
    assert _names(page.tree) == set()

    page.queue_active.setChecked(False)
    assert "Алхимический Огонь" in _names(page.tree)
    assert ui_app.queue.is_active is False

    page.queue_active.setChecked(True)
    assert _names(page.tree) == set()


def test_queue_marks_what_is_short(window, ui_app) -> None:
    ui_app.inventory.set_reagent("shcholkorekh", 2)
    ui_app.queue.add("alkhimicheskiy-ogon", BaseType.LIQUID, {"shcholkorekh": 2})
    ui_app.queue.add("alkhimicheskiy-ogon", BaseType.LIQUID, {"shcholkorekh": 2})
    page = _page(window, CanBrewPage)

    assert page.queue_tree.topLevelItemCount() == 2
    assert page.queue_tree.topLevelItem(0).text(4) == "отложено"
    assert "не хватает" in page.queue_tree.topLevelItem(1).text(4)
    assert "Щёлкорех×2" in page.queue_tree.topLevelItem(1).text(4)


def test_remove_and_clear(window, ui_app) -> None:
    ui_app.inventory.set_reagent("shcholkorekh", 4)
    ui_app.queue.add("alkhimicheskiy-ogon", BaseType.LIQUID, {"shcholkorekh": 2})
    ui_app.queue.add("alkhimicheskiy-ogon", BaseType.VISCOUS, {"shcholkorekh": 2})
    page = _page(window, CanBrewPage)

    page.queue_tree.setCurrentItem(page.queue_tree.topLevelItem(0))
    page._remove_queued()
    assert page.queue_tree.topLevelItemCount() == 1

    ui_app.queue.clear()
    assert page.queue_tree.topLevelItemCount() == 0
    assert page.queue_empty.isVisible()


def test_queue_hides_reserved_from_lab(window, ui_app) -> None:
    """Ответ мастера: в котёл отложенное не попадает."""
    ui_app.inventory.set_reagent("shcholkorekh", 2)
    ui_app.inventory.set_reagent("fanana", 1)
    ui_app.queue.add("alkhimicheskiy-ogon", BaseType.LIQUID, {"shcholkorekh": 2})

    page = _page(window, LabPage)
    assert _names(page.stock) == {"Фанана"}


def test_reagents_page_shows_reserved(window, ui_app) -> None:
    """Ответ мастера: в инвентаре видно, сколько отложено."""
    ui_app.inventory.set_reagent("shcholkorekh", 5)
    ui_app.queue.add("alkhimicheskiy-ogon", BaseType.LIQUID, {"shcholkorekh": 2})

    page = _page(window, ReagentsPage)
    item = next(
        page.tree.topLevelItem(i)
        for i in range(page.tree.topLevelItemCount())
        if page.tree.topLevelItem(i).text(0) == "Щёлкорех"
    )
    assert item.text(3) == "5"
    assert item.text(4) == "2"
    assert "Отложено под очередь: 2 из 5" in item.toolTip(4)


def test_brewing_from_queue_clears_the_entry(window, ui_app) -> None:
    from alchimist.core.models import ResultKind
    from alchimist.services.brewing import BrewRequest

    ui_app.inventory.set_reagent("shcholkorekh", 2)
    ui_app.queue.add("alkhimicheskiy-ogon", BaseType.LIQUID, {"shcholkorekh": 2})
    page = _page(window, CanBrewPage)
    assert page.queue_tree.topLevelItemCount() == 1

    ui_app.brewing.brew(
        BrewRequest(
            base=BaseType.LIQUID,
            reagents={"shcholkorekh": 2},
            result_kind=ResultKind.KNOWN,
            potion_id="alkhimicheskiy-ogon",
        )
    )
    assert page.queue_tree.topLevelItemCount() == 0
    assert ui_app.inventory.potion_qty("alkhimicheskiy-ogon") == 1


# ── кнопки строки: рисует делегат ────────────────────────────────────────────
def _button_rects(page, item):
    """Где в ячейке нарисованы «Сварить» и «В очередь»."""
    cell = page.tree.visualItemRect(item)
    cell.setLeft(page.tree.header().sectionPosition(5))
    cell.setWidth(page.tree.columnWidth(5))
    return cell, page.row_buttons.button_rects(cell)


def _needed_widths(page) -> list[int]:
    """Сколько нужно каждой надписи — по настоящей кнопке с тем же текстом."""
    from PySide6.QtWidgets import QPushButton

    widths = []
    for label in ("Сварить", "В очередь"):
        probe = QPushButton(label, page)
        probe.ensurePolished()
        widths.append(probe.sizeHint().width())
        probe.deleteLater()
    return widths


def _assert_buttons_fit(page) -> None:
    item = page.tree.topLevelItem(0).child(0)
    cell, rects = _button_rects(page, item)
    assert len(rects) == 2
    for rect, needed in zip(rects, _needed_widths(page), strict=True):
        assert rect.width() >= needed
        assert rect.right() <= cell.right(), "кнопка вылезла за колонку"


@pytest.mark.parametrize("point_size", [9, 11, 14, 17])
def test_row_buttons_are_never_clipped(window, ui_app, qapp, point_size) -> None:
    """Колонка с кнопками меряется по ним, а не прибита числом.

    При крупном системном шрифте надпись «В очередь» переставала помещаться:
    ширина колонки была задана константой, подогнанной под один шрифт.
    """
    from PySide6.QtGui import QFont

    original = QFont(qapp.font())
    try:
        font = QFont(original)
        font.setPointSize(point_size)
        qapp.setFont(font)

        ui_app.inventory.set_reagent("shcholkorekh", 2)
        page = _page(window, CanBrewPage)
        page._forget_actions_width()
        page.refresh()
        _assert_buttons_fit(page)
    finally:
        qapp.setFont(original)


def test_buttons_still_fit_after_theme_change(window, ui_app, qapp) -> None:
    """Тема меняет отступы кнопок — ширина колонки должна пересчитаться."""
    from alchimist.core.models import Theme
    from alchimist.ui_qt.theme import apply_theme

    ui_app.inventory.set_reagent("shcholkorekh", 2)
    page = _page(window, CanBrewPage)

    for theme in (Theme.LIGHT, Theme.DARK):
        apply_theme(qapp, theme)
        page.refresh()
        _assert_buttons_fit(page)


def test_rows_have_no_button_widgets(window, ui_app) -> None:
    """Ради этого и делегат: ни одного виджета на строку."""
    ui_app.inventory.set_reagent("shcholkorekh", 2)
    page = _page(window, CanBrewPage)
    top = page.tree.topLevelItem(0)
    assert page.tree.itemWidget(top.child(0), 5) is None
    # У строки зелья кнопок нет — только у вариантов.
    assert page.row_buttons.button_rects(page.tree.visualItemRect(top))  # прямоугольники считаются
    assert not page.row_buttons._has_buttons(page.tree.indexFromItem(top, 5))
    assert page.row_buttons._has_buttons(page.tree.indexFromItem(top.child(0), 5))


def _click_button(qapp, page, item, number) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    _cell, rects = _button_rects(page, item)
    QTest.mouseClick(
        page.tree.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        rects[number].center(),
    )
    qapp.processEvents()


def test_queue_button_click_enqueues(window, ui_app, qapp) -> None:
    ui_app.inventory.set_reagent("shcholkorekh", 2)
    page = _page(window, CanBrewPage)
    item = page.tree.topLevelItem(0).child(0)
    option = item.data(0, ROLE_OPTION)
    _click_button(qapp, page, item, 1)
    entries = ui_app.queue.queue.entries
    assert [e.potion_id for e in entries] == [option.potion.id]


def test_brew_button_click_opens_brewing(window, ui_app, qapp, monkeypatch) -> None:
    ui_app.inventory.set_reagent("shcholkorekh", 2)
    page = _page(window, CanBrewPage)
    item = page.tree.topLevelItem(0).child(0)
    brewed = []
    monkeypatch.setattr(page, "_brew", lambda option: brewed.append(option))
    _click_button(qapp, page, item, 0)
    assert brewed == [item.data(0, ROLE_OPTION)]
    assert ui_app.queue.queue.entries == ()  # «Сварить» в очередь ничего не ставит


def test_click_beside_buttons_does_nothing(window, ui_app, qapp, monkeypatch) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    ui_app.inventory.set_reagent("shcholkorekh", 2)
    page = _page(window, CanBrewPage)
    item = page.tree.topLevelItem(0).child(0)
    monkeypatch.setattr(page, "_brew", lambda option: pytest.fail("нажата кнопка мимо неё"))
    cell, rects = _button_rects(page, item)
    beside = rects[-1].topRight()
    beside.setX(cell.right() - 1)
    QTest.mouseClick(
        page.tree.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, beside
    )
    qapp.processEvents()
    assert ui_app.queue.queue.entries == ()


def test_refresh_keeps_list_focus(window, ui_app, qapp) -> None:
    """Список больше не прячется на время заполнения — фокус с него не слетает."""
    ui_app.inventory.set_reagent("shcholkorekh", 2)
    page = _page(window, CanBrewPage)
    page.tree.setFocus()
    qapp.processEvents()
    if not page.tree.hasFocus():
        pytest.skip("окно без фокуса в этой среде")
    page.refresh()
    qapp.processEvents()
    assert page.tree.hasFocus()


def test_double_click_on_queue_button_is_two_clicks(window, ui_app, qapp, monkeypatch) -> None:
    """Двойной щелчок по «В очередь» — два нажатия кнопки, а не двойной щелчок по строке.

    Строку двойной щелчок варит, но по кнопке он должен остаться кнопке — как было,
    пока кнопки были настоящими виджетами.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    ui_app.inventory.set_reagent("shcholkorekh", 4)
    page = _page(window, CanBrewPage)
    opened = []
    monkeypatch.setattr(page, "_brew", lambda option: opened.append(option))
    page.tree.itemDoubleClicked.disconnect()
    page.tree.itemDoubleClicked.connect(lambda *_a: opened.append("строка"))
    item = page.tree.topLevelItem(0).child(0)
    _cell, rects = _button_rects(page, item)
    viewport, left, none = (
        page.tree.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    at = rects[1].center()
    # Так шлёт события настоящая мышь: нажатие, отпускание, двойной щелчок, отпускание.
    QTest.mousePress(viewport, left, none, at)
    QTest.mouseRelease(viewport, left, none, at)
    QTest.mouseDClick(viewport, left, none, at)
    QTest.mouseRelease(viewport, left, none, at)
    qapp.processEvents()
    assert opened == []
    assert len(ui_app.queue.queue.entries) == 2
