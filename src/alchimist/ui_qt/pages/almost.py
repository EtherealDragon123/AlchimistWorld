"""Страница «Почти готово» (FR-6.1–6.3)."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from alchimist.core.models import RARITY_NAMES_RU
from alchimist.i18n import _
from alchimist.ui_qt.pages.base import Page
from alchimist.ui_qt.theme import bold, muted_color, warning_color
from alchimist.ui_qt.widgets.common import SearchBox, base_text, hint_label, page_heading
from alchimist.ui_qt.widgets.element_badge import rarity_icon


class AlmostPage(Page):
    title = "Почти готово"
    icon = "◔"

    def __init__(self, app, bridge, parent: QWidget | None = None) -> None:
        super().__init__(app, bridge, parent)

        header = QHBoxLayout()
        header.addWidget(page_heading(_("Почти готово")))
        header.addStretch(1)
        header.addWidget(QLabel(_("Не хватает не больше")))
        self.max_missing = QSpinBox()
        self.max_missing.setRange(1, 6)
        self.max_missing.setValue(2)
        self.max_missing.setSuffix(_(" ед."))
        self.max_missing.valueChanged.connect(lambda _v: self.refresh())
        header.addWidget(self.max_missing)
        self.search = SearchBox(_("Поиск…"))
        self.search.setMaximumWidth(240)
        self.search.search.connect(lambda _t: self.refresh())
        header.addWidget(self.search)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels([_("Зелье"), _("Не хватает"), _("Что уже есть / чем закрыть")])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tree.setColumnWidth(0, 280)
        self.tree.setAlternatingRowColors(True)
        self.tree.setIconSize(QSize(10, 10))

        self.empty = hint_label(_("Нечего показать."))
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        box = self.layout_box()
        box.addLayout(header)
        box.addWidget(
            hint_label(
                _(
                    "Сначала то, до чего ближе всего. "
                    "Рядом — реагенты, которые закроют недостачу ровно."
                )
            )
        )
        box.addWidget(self.tree, 1)
        box.addWidget(self.empty)

        self.search.focus_shortcut(self)
        bridge.inventory_changed.connect(self.invalidate)
        bridge.catalog_changed.connect(self.invalidate)
        bridge.settings_changed.connect(self.invalidate)
        bridge.queue_changed.connect(self.invalidate)

    def refresh(self) -> None:
        super().refresh()
        needle = self.search.text().strip().casefold()
        rows = [
            row
            for row in self.app.brewing.almost(max_missing=self.max_missing.value())
            if not needle or needle in row.potion.name.casefold()
        ]

        self.tree.clear()
        self.empty.setVisible(not rows)
        self.tree.setVisible(bool(rows))
        for row in rows:
            have = " + ".join(
                f"{p.ingredient.name}×{p.count}" if p.count > 1 else p.ingredient.name
                for p in row.have.picks
            ) or _("пока ничего")
            # Нехватающая особая основа (П-4.4) — отдельной строкой рядом с элементами.
            missing = [row.missing.format_ru()] if row.missing else []
            if row.missing_base:
                missing.insert(0, _("основа «{name}»").format(name=base_text(self.app, row.base)))
            if row.base_ingredient is not None:
                where = _("на основе «{name}»").format(name=row.base_ingredient.name)
            else:
                where = _("{base} основа").format(base=base_text(self.app, row.base).lower())
            item = QTreeWidgetItem(
                [
                    row.potion.name,
                    ", ".join(missing),
                    _("есть: {have}   ({where})").format(have=have, where=where),
                ]
            )
            item.setIcon(0, rarity_icon(row.potion.rarity))
            item.setFont(0, bold(self.tree.font()))
            item.setForeground(1, warning_color())
            item.setToolTip(0, RARITY_NAMES_RU[row.potion.rarity])
            self.tree.addTopLevelItem(item)

            for filler in row.fillers:
                names = " + ".join(
                    f"{p.ingredient.name}×{p.count}" if p.count > 1 else p.ingredient.name
                    for p in filler.picks
                )
                child = QTreeWidgetItem(["", "", _("закрыть: {names}").format(names=names)])
                child.setForeground(2, muted_color())
                item.addChild(child)
            if not row.fillers:
                child = QTreeWidgetItem(
                    ["", "", _("в справочнике нет реагента, который закрыл бы это ровно")]
                )
                child.setForeground(2, muted_color())
                item.addChild(child)
            item.setExpanded(True)
