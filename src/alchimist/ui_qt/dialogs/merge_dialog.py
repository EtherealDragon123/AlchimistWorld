"""Сравнение справочников при обмене (FR-10.3)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from alchimist.core.models import coerce_enum
from alchimist.i18n import _
from alchimist.services.exchange import Difference, MergeChoice, MergePlan
from alchimist.ui_qt.widgets.common import hint_label

KIND_NAMES = {"ingredient": "реагент", "potion": "зелье"}


class MergeDialog(QDialog):
    """Новое добавится само, по расхождениям игрок выбирает «моё» или «чужое»."""

    def __init__(self, plan: MergePlan, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.plan = plan
        self.setWindowTitle(_("Импорт справочника"))
        self.setMinimumSize(720, 480)

        summary = QLabel(
            _(
                "От кого: {who} ({when})\nНовых: {added}, расхождений: {conflicts}, совпало: {same}"
            ).format(
                who=plan.exported_by or "—",
                when=plan.exported_at[:19] or "—",
                added=len(plan.added),
                conflicts=len(plan.conflicts),
                same=plan.identical,
            )
        )

        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels([_("Запись"), _("Что"), _("Что отличается"), _("Решение")])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tree.setColumnWidth(0, 240)
        self.tree.setColumnWidth(3, 150)

        self._combos: dict[str, QComboBox] = {}

        added_root = QTreeWidgetItem([_("Новые записи"), "", "", ""])
        self.tree.addTopLevelItem(added_root)
        for diff in plan.added:
            item = QTreeWidgetItem([diff.name, KIND_NAMES[diff.kind], _("добавится"), ""])
            added_root.addChild(item)
        added_root.setExpanded(True)

        conflicts_root = QTreeWidgetItem([_("Расхождения"), "", "", ""])
        self.tree.addTopLevelItem(conflicts_root)
        for diff in plan.conflicts:
            item = QTreeWidgetItem([diff.name, KIND_NAMES[diff.kind], self._describe(diff), ""])
            item.setData(0, Qt.ItemDataRole.UserRole, diff.id)
            conflicts_root.addChild(item)
            combo = QComboBox()
            combo.addItem(_("оставить моё"), MergeChoice.KEEP_MINE)
            combo.addItem(_("взять чужое"), MergeChoice.TAKE_THEIRS)
            self._combos[diff.id] = combo
            self.tree.setItemWidget(item, 3, combo)
        conflicts_root.setExpanded(True)

        all_mine = QPushButton(_("Везде оставить моё"))
        all_mine.clicked.connect(lambda: self._set_all(MergeChoice.KEEP_MINE))
        all_theirs = QPushButton(_("Везде взять чужое"))
        all_theirs.clicked.connect(lambda: self._set_all(MergeChoice.TAKE_THEIRS))
        row = QHBoxLayout()
        row.addWidget(all_mine)
        row.addWidget(all_theirs)
        row.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(_("Применить"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(summary)
        layout.addWidget(self.tree, 1)
        layout.addLayout(row)
        layout.addWidget(hint_label(_("Инвентарь и журнал при обмене не передаются (FR-10.4).")))
        layout.addWidget(buttons)

    @staticmethod
    def _describe(diff: Difference) -> str:
        fields = diff.changed_fields()
        mine, theirs = diff.updated_at()
        stamps = _("моё: {mine}, чужое: {theirs}").format(
            mine=(mine or "—")[:19], theirs=(theirs or "—")[:19]
        )
        return f"{', '.join(fields)}   ({stamps})"

    def _set_all(self, choice: MergeChoice) -> None:
        for combo in self._combos.values():
            combo.setCurrentIndex(combo.findData(choice))

    def choices(self) -> dict[str, MergeChoice]:
        """Qt отдаёт из `currentData()` обычную строку, а не сам `StrEnum`."""
        return {
            item_id: coerce_enum(MergeChoice, combo.currentData(), MergeChoice.KEEP_MINE)
            for item_id, combo in self._combos.items()
        }
