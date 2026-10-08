"""Создание персонажа: имя, наборы, а при первом запуске — ещё и тема (FR-14.1)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMessageBox,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from alchimist.core.errors import AlchimistError
from alchimist.core.models import KIT_NAMES_RU, THEME_NAMES_RU, Kit, Theme
from alchimist.i18n import _, describe
from alchimist.ui_qt.theme import apply_theme
from alchimist.ui_qt.widgets.common import hint_label, page_heading

#: Что делать с введённым: создать персонажа. Ошибку (имя занято) показывает диалог.
Create = Callable[[str, tuple[Kit, ...]], object]

#: Ширина карточки с полями, в пикселях: дальше строки только расползаются.
CARD_WIDTH = 520


class CharacterDialog(QDialog):
    """Модальное окно нового персонажа.

    При первом запуске закрыть его, не создав персонажа, значит выйти из приложения:
    без персонажа ни инвентаря, ни изученных рецептов нет (FR-14.1).
    """

    def __init__(
        self,
        create: Create,
        parent: QWidget | None = None,
        *,
        first_run: bool = False,
        theme: Theme = Theme.DARK,
    ) -> None:
        super().__init__(parent)
        self._create = create
        self.first_run = first_run
        self.setWindowTitle(_("Добро пожаловать") if first_run else _("Новый персонаж"))

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(_("Например, Гримли"))
        self.name_edit.textChanged.connect(self._update_ok)

        self.kit_checks: dict[Kit, QCheckBox] = {}
        kits_box = QVBoxLayout()
        for kit in Kit:
            check = QCheckBox(KIT_NAMES_RU[kit])
            check.setChecked(kit is Kit.ALCHEMIST)
            self.kit_checks[kit] = check
            kits_box.addWidget(check)
        kits_box.addWidget(
            hint_label(_("Можно выбрать несколько. Наборы меняются потом в «Настройках»."))
        )

        # Подсказка — прямо под полем, а не отдельной строкой формы с её зазором.
        name_box = QVBoxLayout()
        name_box.setSpacing(4)
        name_box.addWidget(self.name_edit)
        name_box.addWidget(hint_label(_("Имя можно будет поменять в «Настройках».")))

        form = QFormLayout()
        form.addRow(_("Имя"), name_box)
        form.addRow(_("Наборы инструментов"), kits_box)

        # Тема общая на всё приложение, поэтому спрашивается только при первом запуске.
        self.theme_buttons: dict[Theme, QRadioButton] = {}
        if first_run:
            group = QButtonGroup(self)
            row = QHBoxLayout()
            for item in Theme:
                button = QRadioButton(THEME_NAMES_RU[item])
                button.setChecked(item == theme)
                button.toggled.connect(lambda on, t=item: on and self._preview_theme(t))
                group.addButton(button)
                self.theme_buttons[item] = button
                row.addWidget(button)
            row.addStretch(1)
            form.addRow(_("Тема оформления"), row)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.ok_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setText(_("Создать"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            _("Выход") if first_run else _("Отмена")
        )
        self.buttons.accepted.connect(self._confirm)
        self.buttons.rejected.connect(self.reject)

        # Всё содержимое — карточка ограниченной ширины. Окну первого запуска не к чему
        # привязаться, и тайловый оконный менеджер (Hyprland, niri) может развернуть
        # его на весь экран: тогда карточка остаётся по центру, а не растягивается.
        card = QWidget()
        card.setFixedWidth(CARD_WIDTH)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(12)
        card_layout.addWidget(
            page_heading(
                _("Добро пожаловать в AlchimistWorld") if first_run else _("Новый персонаж")
            )
        )
        if first_run:
            intro = QLabel(
                _(
                    "Создайте персонажа. У каждого персонажа свои реагенты, зелья, журнал "
                    "и изученные рецепты, а рецепты обычных зелий он знает с самого начала."
                )
            )
            intro.setWordWrap(True)
            card_layout.addWidget(intro)
        card_layout.addLayout(form)
        card_layout.addSpacing(4)
        card_layout.addWidget(self.buttons)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(card)
        row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        # Размер — ровно по содержимому: окно с фиксированным размером оконные
        # менеджеры обычно показывают плавающим, а не на весь экран.
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        self._update_ok()
        self.name_edit.setFocus()

    # ── значения ──────────────────────────────────────────────────────────
    def name(self) -> str:
        return self.name_edit.text().strip()

    def kits(self) -> tuple[Kit, ...]:
        chosen = tuple(kit for kit, check in self.kit_checks.items() if check.isChecked())
        return chosen or (Kit.ALCHEMIST,)

    def theme(self) -> Theme:
        for item, button in self.theme_buttons.items():
            if button.isChecked():
                return item
        return Theme.DARK

    # ── поведение ─────────────────────────────────────────────────────────
    def _update_ok(self) -> None:
        self.ok_button.setEnabled(bool(self.name()))

    def _preview_theme(self, theme: Theme) -> None:
        """Тему видно сразу, ещё до создания персонажа."""
        application = QApplication.instance()
        if application is not None:
            apply_theme(application, theme)

    def _confirm(self) -> None:
        if not self.name():
            return
        try:
            self._create(self.name(), self.kits())
        except AlchimistError as exc:
            # Имя занято или зарезервировано: окно остаётся, ввод не теряется.
            QMessageBox.warning(self, _("Не получилось"), describe(exc.message))
            return
        self.accept()
