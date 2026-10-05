"""Страница «Мои зелья»: инвентарь готовых зелий (FR-4.x)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from alchimist.core.errors import AlchimistError
from alchimist.core.models import KIND_NAMES_RU, RARITY_NAMES_RU
from alchimist.i18n import _, describe
from alchimist.ui_qt.markdown import to_html
from alchimist.ui_qt.pages.base import Page
from alchimist.ui_qt.theme import rarity_color
from alchimist.ui_qt.widgets.common import SearchBox, hint_label, page_heading


class AddPotionDialog(QDialog):
    """Зелье без варки: купил, нашёл, дали (FR-4.3)."""

    def __init__(self, app, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.chosen: str | None = None
        self.setWindowTitle(_("Добавить зелье"))
        self.setMinimumWidth(460)

        self.search = QLineEdit()
        self.search.setPlaceholderText(_("Начните вводить название…"))
        self.list = QListWidget()
        self.qty = QComboBox()
        self.qty.setEditable(True)
        for value in range(1, 21):
            self.qty.addItem(str(value), value)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        row = QHBoxLayout()
        row.addWidget(QLabel(_("Сколько")))
        row.addWidget(self.qty)
        row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.search)
        layout.addWidget(self.list, 1)
        layout.addLayout(row)
        layout.addWidget(buttons)

        self.search.textChanged.connect(self._filter)
        self.list.itemDoubleClicked.connect(lambda _i: self._accept())
        self._filter("")

    def _filter(self, text: str) -> None:
        needle = text.strip().casefold()
        self.list.clear()
        for potion in self.app.catalog.potions():
            if needle and needle not in potion.name.casefold():
                continue
            entry = QListWidgetItem(
                f"{potion.name}   ·   {RARITY_NAMES_RU[potion.rarity]}   ·   "
                f"{KIND_NAMES_RU[potion.kind]}"
            )
            entry.setData(Qt.ItemDataRole.UserRole, potion.id)
            self.list.addItem(entry)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _accept(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        self.chosen = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def quantity(self) -> int:
        try:
            return max(1, int(self.qty.currentText()))
        except ValueError:
            return 1


class MyPotionsPage(Page):
    title = "Мои зелья"
    icon = "🍶"

    def __init__(self, app, bridge, parent: QWidget | None = None) -> None:
        super().__init__(app, bridge, parent)

        header = QHBoxLayout()
        header.addWidget(page_heading(_("Мои зелья")))
        header.addStretch(1)
        self.search = SearchBox(_("Поиск…"))
        self.search.setMaximumWidth(260)
        self.search.search.connect(lambda _t: self.refresh())
        header.addWidget(self.search)
        add_button = QPushButton(_("Добавить…"))
        add_button.clicked.connect(self._add)
        header.addWidget(add_button)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels([_("Зелье"), _("Редкость"), _("Вид"), _("Штук"), _("Заметка")])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            self.tree.header().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.tree.setColumnWidth(4, 160)
        self.tree.setAlternatingRowColors(True)
        self.tree.currentItemChanged.connect(lambda _c, _p: self._show_description())

        self.description = QTextBrowser()
        self.description.setOpenExternalLinks(False)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.description)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        buttons = QHBoxLayout()
        use_button = QPushButton(_("Использовать"))
        use_button.setToolTip(_("−1 шт. и запись в журнал"))
        use_button.clicked.connect(self._use)
        buttons.addWidget(use_button)
        for text, delta in ((_("−1"), -1), (_("+1"), 1)):
            button = QPushButton(text)
            button.clicked.connect(lambda _c=False, d=delta: self._step(d))
            buttons.addWidget(button)
        note_button = QPushButton(_("Заметка…"))
        note_button.clicked.connect(self._edit_note)
        buttons.addWidget(note_button)
        buttons.addStretch(1)

        box = self.layout_box()
        box.addLayout(header)
        box.addWidget(splitter, 1)
        box.addLayout(buttons)
        box.addWidget(
            hint_label(_("«Использовать» уменьшает количество на 1 и пишет запись в журнал."))
        )

        self.search.focus_shortcut(self)
        bridge.inventory_changed.connect(self.invalidate)
        bridge.catalog_changed.connect(self.invalidate)

    def refresh(self) -> None:
        super().refresh()
        needle = self.search.text().strip().casefold()
        current = self._selected_id()
        self.tree.clear()
        for row in self.app.inventory.potion_rows(self.app.catalog.potion_map()):
            if needle and needle not in row.potion.name.casefold():
                continue
            item = QTreeWidgetItem(
                [
                    row.potion.name,
                    RARITY_NAMES_RU[row.potion.rarity],
                    KIND_NAMES_RU[row.potion.kind],
                    str(row.qty),
                    row.note,
                ]
            )
            item.setForeground(1, rarity_color(row.potion.rarity))
            item.setData(0, Qt.ItemDataRole.UserRole, row.potion.id)
            item.setTextAlignment(3, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tree.addTopLevelItem(item)
            if row.potion.id == current:
                self.tree.setCurrentItem(item)
        if self.tree.currentItem() is None and self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self._show_description()

    def _selected_id(self) -> str | None:
        item = self.tree.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item else None

    def _show_description(self) -> None:
        potion_id = self._selected_id()
        if not potion_id:
            self.description.clear()
            return
        potion = self.app.catalog.potion(potion_id)
        recipe = (
            f"{potion.recipe.format_bases_ru()} · {potion.recipe.elements.format_ru()}"
            if potion.recipe
            else _("неизвестен")
        )
        self.description.setHtml(
            f"<h3>{potion.name}</h3>"
            f"<p><i>{RARITY_NAMES_RU[potion.rarity]} · {KIND_NAMES_RU[potion.kind]}"
            f" · {_('рецепт')}: {recipe}</i></p>" + to_html(potion.description_md)
        )

    def _add(self) -> None:
        dialog = AddPotionDialog(self.app, self)
        if dialog.exec() and dialog.chosen:
            self.app.inventory.add_potion(dialog.chosen, dialog.quantity())

    def _use(self) -> None:
        potion_id = self._selected_id()
        if not potion_id:
            return
        try:
            self.app.brewing.use_potion(potion_id)
        except AlchimistError as exc:
            QMessageBox.warning(self, _("Не получилось"), describe(exc.message))

    def _step(self, delta: int) -> None:
        potion_id = self._selected_id()
        if potion_id:
            self.app.inventory.add_potion(potion_id, delta)

    def _edit_note(self) -> None:
        potion_id = self._selected_id()
        if not potion_id:
            return
        rows = {
            r.potion.id: r.note
            for r in self.app.inventory.potion_rows(self.app.catalog.potion_map())
        }
        text, ok = QInputDialog.getText(
            self, _("Заметка"), _("Заметка к позиции"), text=rows.get(potion_id, "")
        )
        if ok:
            self.app.inventory.set_potion_note(potion_id, text.strip())
