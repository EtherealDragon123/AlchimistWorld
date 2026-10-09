"""Персонажи в интерфейсе: первый запуск, настройки, справочник игрока (FR-14.x)."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QMessageBox

from alchimist.core.models import BaseType, Kit, Outcome, ResultKind, Theme
from alchimist.services import build_app
from alchimist.ui_qt.dialogs.brew_dialog import BrewDialog
from alchimist.ui_qt.dialogs.character_dialog import CharacterDialog
from alchimist.ui_qt.pages.catalog import CatalogPage
from alchimist.ui_qt.pages.settings import SettingsPage

SALAMANDER = "plamya-salamandry"


@pytest.fixture
def campaign(tmp_path, qapp):
    """Настоящая установка: справочник кампании и игрок «Айн» со стартовыми знаниями."""
    service = build_app(tmp_path / "campaign")
    service.create_character("Айн")
    return service


@pytest.fixture
def campaign_window(campaign, qapp):
    from alchimist.ui_qt.main_window import MainWindow

    window = MainWindow(campaign)
    window.show()
    qapp.processEvents()
    yield window
    window.close()


@pytest.fixture
def keep_theme(qapp):
    """Предпросмотр темы меняет оформление всего приложения: после теста вернуть.

    Возвращается само состояние Qt, а не «тема»: тесты по умолчанию идут без общей
    таблицы стилей, а с ней каждый следующий виджет создаётся заметно дольше.
    """
    from alchimist.ui_qt import theme

    sheet, palette = qapp.styleSheet(), qapp.palette()
    current, applied = theme._current, theme._style_applied
    yield
    qapp.setStyleSheet(sheet)
    qapp.setPalette(palette)
    theme._current, theme._style_applied = current, applied


def page_of(window, page_class):
    window.go_to(page_class)
    return next(p for p in window.pages if isinstance(p, page_class))


# ── окно создания (FR-14.1) ──────────────────────────────────────────────────
def test_first_run_dialog_defaults_and_creates(tmp_path, qapp, keep_theme) -> None:
    service = build_app(tmp_path)
    dialog = CharacterDialog(
        lambda name, kits: service.create_character(name, kits), first_run=True
    )
    assert dialog.theme() is Theme.DARK  # по умолчанию тёмная
    assert not dialog.ok_button.isEnabled()  # без имени создавать нечего

    dialog.name_edit.setText("Айн")
    dialog.kit_checks[Kit.ALCHEMIST].setChecked(False)
    dialog.kit_checks[Kit.HERBALIST].setChecked(True)
    dialog.theme_buttons[Theme.LIGHT].setChecked(True)
    dialog._confirm()

    assert dialog.result() == CharacterDialog.DialogCode.Accepted
    assert dialog.theme() is Theme.LIGHT
    assert service.characters.active.name == "Айн"
    assert service.characters.kits == (Kit.HERBALIST,)


def test_dialog_keeps_input_on_taken_name(campaign, qapp, monkeypatch) -> None:
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    dialog = CharacterDialog(lambda name, kits: campaign.create_character(name, kits))
    assert not dialog.theme_buttons  # тема спрашивается только при первом запуске
    dialog.name_edit.setText("айн")
    dialog._confirm()
    assert shown and "уже занято" in shown[0]
    assert dialog.result() != CharacterDialog.DialogCode.Accepted
    assert dialog.name_edit.text() == "айн"


def test_first_run_exit_means_no_window(tmp_path, qapp, monkeypatch) -> None:
    from alchimist.ui_qt.app import first_run

    service = build_app(tmp_path)
    monkeypatch.setattr(CharacterDialog, "exec", lambda self: 0)
    assert first_run(service) is False
    assert not service.characters.has_characters


# ── настройки (FR-14.5) ──────────────────────────────────────────────────────
def test_settings_switch_character_and_title(campaign, campaign_window, qapp) -> None:
    campaign.create_character("Гримли", (Kit.POISONER,))
    page = page_of(campaign_window, SettingsPage)
    names = [page.character_combo.itemText(i) for i in range(page.character_combo.count())]
    assert names == ["Айн", "Гримли"]
    assert campaign_window.windowTitle() == "AlchimistWorld — Гримли"
    assert page.kit_checks[Kit.POISONER].isChecked()
    assert page.delete_button.isEnabled()

    page.character_combo.setCurrentIndex(0)
    qapp.processEvents()
    assert campaign.characters.active.name == "Айн"
    assert campaign_window.windowTitle() == "AlchimistWorld — Айн"
    assert page.kit_checks[Kit.ALCHEMIST].isChecked()
    assert not page.kit_checks[Kit.POISONER].isChecked()


def test_settings_show_gm_only_controls(campaign, campaign_window) -> None:
    page = page_of(campaign_window, SettingsPage)
    assert not page.export_button.isVisibleTo(page)
    assert not page.role_label.isVisibleTo(page)

    campaign.create_character("GM")
    assert page.export_button.isVisibleTo(page)
    assert page.role_label.isVisibleTo(page)
    assert not page.rename_button.isEnabled()  # имя GM фиксированное


# ── справочник глазами игрока (FR-14.3, FR-14.4) ─────────────────────────────
def _select(tab, potion_id) -> None:
    for row in range(tab.tree.topLevelItemCount()):
        item = tab.tree.topLevelItem(row)
        if item.data(0, 0x0100) == potion_id:
            tab.tree.setCurrentItem(item)
            return
    raise AssertionError(f"{potion_id} нет в списке")


def _recipe_cell(tab, potion_id) -> str:
    for row in range(tab.tree.topLevelItemCount()):
        item = tab.tree.topLevelItem(row)
        if item.data(0, 0x0100) == potion_id:
            return item.text(3)
    raise AssertionError(f"{potion_id} нет в списке")


def test_player_learns_from_the_catalog(campaign, campaign_window) -> None:
    page = page_of(campaign_window, CatalogPage)
    tab = page.potions
    assert not any(b.isVisibleTo(tab) for b in tab.gm_buttons)
    assert tab.learn_button.isVisibleTo(tab)
    assert _recipe_cell(tab, SALAMANDER) == "не изучен"
    assert _recipe_cell(tab, "zele-nevidimosti") == "неизвестен"

    _select(tab, SALAMANDER)
    assert tab.learn_button.isEnabled() and not tab.forget_button.isEnabled()
    tab.learn()
    assert campaign.characters.active.knows(SALAMANDER)
    assert _recipe_cell(tab, SALAMANDER) == "Вязкая · Огонь×2, Свет×1"


def test_player_can_hide_unlearned(campaign, campaign_window) -> None:
    tab = page_of(campaign_window, CatalogPage).potions
    total = tab.tree.topLevelItemCount()
    tab.unknown_check.setChecked(False)
    assert not campaign.characters.active.show_unknown
    tab = page_of(campaign_window, CatalogPage).potions
    assert tab.tree.topLevelItemCount() == 20  # только изученные: обычные
    assert tab.tree.topLevelItemCount() < total


def test_gm_sees_editing_buttons(campaign, campaign_window) -> None:
    campaign.create_character("GM")
    tab = page_of(campaign_window, CatalogPage).potions
    assert all(b.isVisibleTo(tab) for b in tab.gm_buttons)
    assert not tab.learn_button.isVisibleTo(tab)
    assert _recipe_cell(tab, SALAMANDER) == "Вязкая · Огонь×2, Свет×1"


# ── находка при варке (FR-14.7) ──────────────────────────────────────────────
def test_exact_successful_brew_offers_to_learn(campaign, qapp, monkeypatch) -> None:
    asked = []

    def answer(*args, **kwargs):
        asked.append(args[2])
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", answer)
    campaign.inventory.set_reagent("shchelkorekh", 2)
    campaign.inventory.set_reagent("svechnaya-roza", 1)
    dialog = BrewDialog(campaign, BaseType.VISCOUS, {"shchelkorekh": 2, "svechnaya-roza": 1})
    assert not dialog.create_potion.isVisibleTo(dialog)  # заводить зелья — дело GM
    # Неизученный рецепт заранее не раскрывается: в подсказке только известное.
    assert "Пламя Саламандры" not in dialog.hint._label.text()
    dialog.result_kind.setCurrentIndex(dialog.result_kind.findData(ResultKind.NOTHING))
    dialog._confirm()

    assert asked and "Пламя Саламандры" in asked[0]
    assert campaign.characters.active.knows(SALAMANDER)
    assert dialog.outcome.entry.outcome is Outcome.SUCCESS


def test_failed_brew_reveals_nothing(campaign, qapp, monkeypatch) -> None:
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: pytest.fail("провал не должен ничего открывать")
    )
    campaign.inventory.set_reagent("shchelkorekh", 2)
    campaign.inventory.set_reagent("svechnaya-roza", 1)
    dialog = BrewDialog(campaign, BaseType.VISCOUS, {"shchelkorekh": 2, "svechnaya-roza": 1})
    dialog.failure.setChecked(True)
    dialog._confirm()
    assert not campaign.characters.active.knows(SALAMANDER)


# ── изучение реагентов (FR-14.9–14.11) ───────────────────────────────────────
KAVA = "koren-kavy"  # необычное растение: новичок его не знает
NUT = "shchelkorekh"  # обычное: его знают все


def test_player_learns_a_reagent_in_the_catalog(campaign, campaign_window, monkeypatch) -> None:
    tab = page_of(campaign_window, CatalogPage).ingredients
    assert tab.learn_button.isVisibleTo(tab) and tab.forget_button.isVisibleTo(tab)
    assert _recipe_cell(tab, KAVA) == "не изучен"
    _select(tab, KAVA)
    assert "не изучен" in tab.card.toPlainText()
    assert tab.learn_button.isEnabled() and not tab.forget_button.isEnabled()

    tab.learn()
    tab = page_of(campaign_window, CatalogPage).ingredients
    assert _recipe_cell(tab, KAVA) == "Вода×1, Магия×1"
    _select(tab, KAVA)
    assert not tab.learn_button.isEnabled() and tab.forget_button.isEnabled()

    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Yes)
    tab.forget()
    assert not campaign.catalog.knows_ingredient(KAVA)


def test_reagent_in_the_bag_or_common_cannot_be_forgotten(campaign, campaign_window) -> None:
    campaign.inventory.set_reagent(KAVA, 1)  # попал в сумку — изучен
    tab = page_of(campaign_window, CatalogPage).ingredients
    _select(tab, KAVA)
    assert not tab.forget_button.isEnabled()
    assert "в сумке" in tab.forget_button.toolTip()

    _select(tab, NUT)
    assert not tab.learn_button.isEnabled() and not tab.forget_button.isEnabled()
    assert "знают все" in tab.forget_button.toolTip()


def test_hiding_unlearned_hides_reagents_too(campaign, campaign_window) -> None:
    tab = page_of(campaign_window, CatalogPage).ingredients
    assert tab.tree.topLevelItemCount() == 63
    tab.unknown_check.setChecked(False)
    page = page_of(campaign_window, CatalogPage)
    assert page.ingredients.tree.topLevelItemCount() == 55
    assert not page.potions.unknown_check.isChecked()  # одна настройка на обе вкладки


def test_add_dialog_shows_unlearned_without_elements(campaign, qapp) -> None:
    from alchimist.ui_qt.pages.reagents import AddReagentDialog

    dialog = AddReagentDialog(campaign)
    rows = [dialog.list.item(i).text() for i in range(dialog.list.count())]
    assert any("Корень кавы" in r and "не изучен" in r for r in rows)
    assert any("Щёлкорех" in r and "Огонь×1" in r for r in rows)
    assert dialog.unknown_hint.isVisibleTo(dialog)
    dialog.search.setText("Щёлкорех")
    assert not dialog.unknown_hint.isVisibleTo(dialog)  # среди найденного неизученных нет
    dialog.close()


def test_gm_sees_reagents_whole(campaign, campaign_window) -> None:
    campaign.create_character("GM")
    tab = page_of(campaign_window, CatalogPage).ingredients
    assert not tab.learn_button.isVisibleTo(tab)
    assert _recipe_cell(tab, KAVA) == "Вода×1, Магия×1"
