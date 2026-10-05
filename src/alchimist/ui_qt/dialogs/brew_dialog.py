"""Диалог варки (FR-7.1, FR-7.2, FR-7.5)."""

from __future__ import annotations

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from alchimist.core.errors import AlchimistError
from alchimist.core.matcher import Combination, portions_and_excess
from alchimist.core.models import (
    BASE_NAMES_RU,
    BASE_ORDER,
    BaseType,
    Outcome,
    Potion,
    ResultKind,
    coerce_enum,
)
from alchimist.core.rules import brew_difficulty
from alchimist.i18n import _, describe
from alchimist.services.app import AppService
from alchimist.services.brewing import BrewOutcome, BrewRequest
from alchimist.ui_qt.theme import accent_color, bold, warning_color
from alchimist.ui_qt.widgets.common import (
    MessageStrip,
    difficulty_tooltip,
    format_difficulty,
    hint_label,
)
from alchimist.ui_qt.widgets.element_counter import ElementCounters


def combination_text(combination: Combination) -> str:
    return " + ".join(
        f"{p.ingredient.name}×{p.count}" if p.count > 1 else p.ingredient.name
        for p in combination.picks
    )


class BrewDialog(QDialog):
    """Основа, реагенты, сумма элементов, ожидаемое зелье, количество, исход, заметка."""

    def __init__(
        self,
        app: AppService,
        base: BaseType,
        reagents: dict[str, int],
        parent: QWidget | None = None,
        *,
        expected: Potion | None = None,
    ) -> None:
        super().__init__(parent)
        self.app = app
        self.reagents = dict(reagents)
        self.outcome: BrewOutcome | None = None
        #: Пока игрок не трогал список зелий, диалог подставляет туда самое простое.
        self._potion_touched = False
        #: То же для порций: пока не трогали, варим по максимуму.
        self._portions_touched = False
        self.setWindowTitle(_("Варка"))
        self.setMinimumWidth(560)

        ingredients = app.catalog.ingredient_map()
        self.base = QComboBox()
        for item in BASE_ORDER:
            self.base.addItem(BASE_NAMES_RU[item], item)
        self.base.setCurrentIndex(BASE_ORDER.index(base))

        self.reagent_list = QListWidget()
        self.reagent_list.setMaximumHeight(120)
        for ingredient_id, qty in sorted(self.reagents.items()):
            ingredient = ingredients.get(ingredient_id)
            name = ingredient.name if ingredient else ingredient_id
            elements = ingredient.elements.format_ru() if ingredient else ""
            self.reagent_list.addItem(f"{qty} × {name}    {elements}")

        self.elements = ElementCounters(read_only=True, columns=2)
        self.elements.set_vector(app.brewing.combination_elements(self.reagents))

        self.success = QRadioButton(_("Успех"))
        self.failure = QRadioButton(_("Провал"))
        self.success.setChecked(True)

        self.result_kind = QComboBox()
        for kind, text in (
            (ResultKind.KNOWN, _("Известное зелье")),
            (ResultKind.NEW, _("Новое зелье")),
            (ResultKind.NOTHING, _("Ничего не вышло")),
            (ResultKind.JABBERWOCK, _("Бармаглот")),
        ):
            self.result_kind.addItem(text, kind)

        self.potion = QComboBox()
        self.potion.setEditable(False)
        self._fill_potions()
        # FR-7.5: если открыли что-то новое, зелье заводится прямо отсюда.
        self.create_potion = QPushButton(_("Создать…"))
        self.create_potion.setToolTip(_("Завести новое зелье в справочнике"))
        self.create_potion.clicked.connect(self._create_potion)

        self.portions = QSpinBox()
        self.portions.setRange(1, 99)
        self.portions.setValue(1)
        self.portions.setToolTip(
            _("Сколько порций варится за раз. Столько же зелий и получится (П-8.2).")
        )
        self.portions.valueChanged.connect(self._portions_changed)

        self.difficulty_label = QLabel()
        self.difficulty_label.setFont(bold(self.difficulty_label.font()))
        self.excess_label = QLabel()
        self.excess_label.setObjectName("hint")

        self.note = QLineEdit()
        self.note.setPlaceholderText(_("Заметка к записи журнала"))
        self.hint = MessageStrip()

        form = QFormLayout()
        form.addRow(_("Основа"), self.base)
        form.addRow(_("Реагенты"), self.reagent_list)
        form.addRow(_("Сумма элементов"), self.elements)

        outcome_row = QHBoxLayout()
        outcome_row.addWidget(self.success)
        outcome_row.addWidget(self.failure)
        outcome_row.addStretch(1)

        result_box = QGroupBox(_("Что вышло"))
        result_form = QFormLayout(result_box)
        result_form.addRow(_("Исход"), outcome_row)
        result_form.addRow(_("Результат"), self.result_kind)
        potion_row = QHBoxLayout()
        potion_row.addWidget(self.potion, 1)
        potion_row.addWidget(self.create_potion)
        result_form.addRow(_("Зелье"), potion_row)
        result_form.addRow(_("Порций"), self.portions)
        result_form.addRow(_("Лишние эссенции"), self.excess_label)
        result_form.addRow(_("Сложность броска"), self.difficulty_label)
        result_form.addRow(_("Заметка"), self.note)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(_("Сварить"))
        self.buttons.accepted.connect(self._confirm)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.hint)
        layout.addWidget(result_box)
        layout.addWidget(hint_label(_("Ctrl+Enter — сварить. Кубы бросаются за столом (П-7.2).")))
        layout.addWidget(self.buttons)

        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(self._confirm)

        self.base.currentIndexChanged.connect(self._refresh)
        self.success.toggled.connect(self._refresh)
        self.result_kind.currentIndexChanged.connect(self._refresh)
        self.potion.currentIndexChanged.connect(self._potion_changed)

        if expected is not None:
            self._select_potion(expected.id)
        self._refresh()

    # ── наполнение ────────────────────────────────────────────────────────
    def _fill_potions(self) -> None:
        self.potion.clear()
        for potion in self.app.catalog.potions():
            self.potion.addItem(potion.name, potion.id)

    def _select_potion(self, potion_id: str) -> None:
        """Подставляет зелье, не считая это выбором игрока."""
        index = self.potion.findData(potion_id)
        if index >= 0:
            was_touched = self._potion_touched
            self.potion.setCurrentIndex(index)
            self._potion_touched = was_touched

    def _kind(self) -> ResultKind:
        """Qt разворачивает `StrEnum` в обычную строку, а сравнения тут по `is`."""
        return coerce_enum(ResultKind, self.result_kind.currentData(), ResultKind.NONE)

    def _refresh(self) -> None:
        success = self.success.isChecked()
        self.result_kind.setEnabled(success)
        kind = self._kind()
        needs_potion = success and kind in (
            ResultKind.KNOWN,
            ResultKind.NEW,
            ResultKind.JABBERWOCK,
        )
        self.potion.setEnabled(needs_potion)
        self.create_potion.setEnabled(needs_potion)
        self.portions.setEnabled(needs_potion)
        self._refresh_difficulty(needs_potion)

        base = self.base.currentData()
        hint = self.app.brewing.hint(base, self.reagents)
        lines: list[str] = []
        if hint.matches:
            names = ", ".join(f"«{p.name}»" for p in hint.matches)
            lines.append(
                f'<span style="color:{accent_color().name()}">'
                + _("Совпадает с рецептом: {names}").format(names=names)
                + "</span>"
            )
            if (
                success
                and kind is ResultKind.KNOWN
                and not self._potion_touched
                and self.potion.currentData() not in {p.id for p in hint.matches}
            ):
                self._select_potion(hint.matches[0].id)
        else:
            lines.append(_("Неизвестная комбинация: рецепта на такую сумму нет"))
        if hint.was_tried:
            last = hint.history[0]
            lines.append(
                _("Эту комбинацию уже пробовали: {result}").format(result=_outcome_text(last))
            )
        if self.app.settings.kits and not hint.allowed_kits:
            lines.append(
                f'<span style="color:{warning_color().name()}">'
                + _("Выбранные наборы такую варку не разрешают (П-6.3)")
                + "</span>"
            )
        self.hint.show_text("<br>".join(lines))

    def _create_potion(self) -> None:
        """Быстрое создание зелья из диалога варки (FR-7.5)."""
        from alchimist.ui_qt.dialogs.potion_dialog import PotionDialog

        dialog = PotionDialog(self.app, None, self)
        if not dialog.exec():
            return
        try:
            potion, messages = self.app.add_potion(dialog.build())
        except AlchimistError as exc:
            QMessageBox.warning(self, _("Не получилось"), describe(exc.message))
            return
        if messages:
            QMessageBox.warning(
                self,
                _("Сохранено с предупреждениями"),
                "\n".join(describe(m) for m in messages),
            )
        self._fill_potions()
        self._select_potion(potion.id)

    def _portions_changed(self) -> None:
        self._portions_touched = True
        self._refresh()

    def _potion_changed(self) -> None:
        """Игрок выбрал зелье сам: больше не подставляем своё, но пересчитываем."""
        self._potion_touched = True
        self._refresh_difficulty(self.potion.isEnabled())

    def _refresh_difficulty(self, active: bool) -> None:
        """Сложность и остаток считаются по рецепту выбранного зелья (П-8)."""
        potion_id = self.potion.currentData()
        if not active or not potion_id:
            self.difficulty_label.setText("—")
            self.difficulty_label.setToolTip("")
            self.excess_label.setText("—")
            self.portions.setMaximum(99)
            return

        potion = self.app.catalog.potion(potion_id)
        elements = self.elements.vector()
        possible, _rest = (
            portions_and_excess(elements, potion.recipe.elements)
            if potion.recipe
            else (0, elements)
        )

        if potion.recipe is None or possible <= 0:
            # Рецепта нет или элементов не хватает: сложность считать не по чему.
            self.portions.setMaximum(99)
            self.difficulty_label.setText(
                _("по рецепту не считается") if potion.recipe is None else _("элементов не хватает")
            )
            self.difficulty_label.setToolTip("")
            self.excess_label.setText("—")
            return

        if self.portions.maximum() != possible:
            self.portions.setMaximum(possible)
            # По умолчанию варим всё, на что хватило: реагенты всё равно уже
            # потрачены, а лишняя порция обходится дешевле того же объёма
            # лишних эссенций (П-8.1 против П-8.2).
            if not self._portions_touched:
                self.portions.blockSignals(True)
                self.portions.setValue(possible)
                self.portions.blockSignals(False)
        portions = min(self.portions.value(), possible)
        excess = elements - potion.recipe.elements * portions
        difficulty = brew_difficulty(potion.rarity, portions, excess.total)
        self.difficulty_label.setText(format_difficulty(difficulty))
        self.difficulty_label.setToolTip(difficulty_tooltip(difficulty))
        self.excess_label.setText(excess.format_ru() if excess else _("нет"))

    # ── подтверждение ─────────────────────────────────────────────────────
    def request(self) -> BrewRequest:
        success = self.success.isChecked()
        kind = self._kind() if success else ResultKind.NONE
        needs_potion = success and kind in (
            ResultKind.KNOWN,
            ResultKind.NEW,
            ResultKind.JABBERWOCK,
        )
        return BrewRequest(
            base=self.base.currentData(),
            reagents=self.reagents,
            outcome=Outcome.SUCCESS if success else Outcome.FAILURE,
            result_kind=kind,
            potion_id=self.potion.currentData() if needs_potion else None,
            portions=self.portions.value() if needs_potion else 1,
            note=self.note.text().strip(),
        )

    def _confirm(self) -> None:
        try:
            self.outcome = self.app.brewing.brew(self.request())
        except AlchimistError as exc:
            QMessageBox.warning(self, _("Не получилось"), describe(exc.message))
            return
        self.accept()


def _outcome_text(entry) -> str:
    if entry.outcome is Outcome.FAILURE:
        return _("провал")
    if entry.result is None:
        return _("неизвестно")
    match entry.result.kind:
        case ResultKind.NOTHING:
            return _("ничего не вышло")
        case ResultKind.JABBERWOCK:
            return _("получился Бармаглот")
        case _:
            return _("получилось зелье")
