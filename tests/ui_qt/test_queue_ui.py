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


# ── размеры кнопок ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("point_size", [9, 11, 14, 17])
def test_row_buttons_are_never_clipped(window, ui_app, qapp, point_size) -> None:
    """Колонка с кнопками меряется по ним, а не прибита числом.

    При крупном системном шрифте надпись «В очередь» переставала помещаться:
    ширина колонки была задана константой, подогнанной под один шрифт.
    """
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QPushButton

    original = QFont(qapp.font())
    try:
        font = QFont(original)
        font.setPointSize(point_size)
        qapp.setFont(font)

        ui_app.inventory.set_reagent("shcholkorekh", 2)
        page = _page(window, CanBrewPage)
        page._forget_actions_width()
        page.refresh()

        top = page.tree.topLevelItem(0)
        actions = page.tree.itemWidget(top.child(0), 5)
        buttons = actions.findChildren(QPushButton)
        assert len(buttons) == 2
        for button in buttons:
            assert button.width() >= button.sizeHint().width(), (
                f"{button.text()!r} обрезана при {point_size}pt: "
                f"дали {button.width()}, нужно {button.sizeHint().width()}"
            )
    finally:
        qapp.setFont(original)


def test_buttons_still_fit_after_theme_change(window, ui_app, qapp) -> None:
    """Тема меняет отступы кнопок — ширина колонки должна пересчитаться."""
    from PySide6.QtWidgets import QPushButton

    from alchimist.core.models import Theme
    from alchimist.ui_qt.theme import apply_theme

    ui_app.inventory.set_reagent("shcholkorekh", 2)
    page = _page(window, CanBrewPage)

    for theme in (Theme.LIGHT, Theme.DARK):
        apply_theme(qapp, theme)
        page.refresh()
        actions = page.tree.itemWidget(page.tree.topLevelItem(0).child(0), 5)
        for button in actions.findChildren(QPushButton):
            assert button.width() >= button.sizeHint().width(), (theme, button.text())
