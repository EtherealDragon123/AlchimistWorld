"""Страница «Настройки»: наборы, тема, папка данных, импорт и экспорт (FR-9.x, FR-10.x)."""

from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from alchimist.core.errors import AlchimistError
from alchimist.core.models import KIT_NAMES_RU, THEME_NAMES_RU, Kit, Theme
from alchimist.i18n import _, describe
from alchimist.ui_qt.dialogs.merge_dialog import MergeDialog
from alchimist.ui_qt.pages.base import Page
from alchimist.ui_qt.widgets.common import hint_label, page_heading


class SettingsPage(Page):
    title = "Настройки"
    icon = "⚙"

    def __init__(self, app, bridge, parent: QWidget | None = None) -> None:
        super().__init__(app, bridge, parent)

        # ── наборы (FR-9.1) ───────────────────────────────────────────────
        kits_box = QGroupBox(_("Наборы инструментов"))
        kits_layout = QVBoxLayout(kits_box)
        self.kit_checks: dict[Kit, QCheckBox] = {}
        for kit in Kit:
            check = QCheckBox(KIT_NAMES_RU[kit])
            check.toggled.connect(lambda _v: self._save_kits())
            self.kit_checks[kit] = check
            kits_layout.addWidget(check)
        kits_layout.addWidget(
            hint_label(
                _(
                    "Можно выбрать несколько. Вариант доступен, если его разрешает хотя бы один "
                    "набор, но смешивать права разных наборов в одной варке нельзя (П-6.3)."
                )
            )
        )

        # ── персонаж и тема ───────────────────────────────────────────────
        profile_box = QGroupBox(_("Персонаж"))
        profile_form = QFormLayout(profile_box)
        self.character = QLineEdit()
        self.character.editingFinished.connect(self._save_character)
        profile_form.addRow(_("Имя персонажа"), self.character)
        self.theme = QComboBox()
        for theme in Theme:
            self.theme.addItem(THEME_NAMES_RU[theme], theme)
        self.theme.currentIndexChanged.connect(self._save_theme)
        profile_form.addRow(_("Тема оформления"), self.theme)
        # Выбор языка вернётся вместе с переводом (FR-9.3, FR-11.4): пока английский
        # каталог пуст, и пункт «English» только вводил бы в заблуждение.

        # ── папка данных (FR-9.4) ─────────────────────────────────────────
        data_box = QGroupBox(_("Данные"))
        data_layout = QVBoxLayout(data_box)
        self.data_path = QLabel()
        self.settings_path = QLabel()
        for label in (self.data_path, self.settings_path):
            label.setTextInteractionFlags(
                label.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse
            )
            label.setWordWrap(True)
            data_layout.addWidget(label)
        row = QHBoxLayout()
        open_button = QPushButton(_("Открыть папку"))
        open_button.clicked.connect(self._open_folder)
        row.addWidget(open_button)
        backup_button = QPushButton(_("Резервная копия в zip…"))
        backup_button.clicked.connect(self._backup)
        row.addWidget(backup_button)
        row.addStretch(1)
        data_layout.addLayout(row)

        # ── обмен и импорт (FR-10.x) ──────────────────────────────────────
        exchange_box = QGroupBox(_("Справочник"))
        exchange_layout = QVBoxLayout(exchange_box)
        exchange_row = QHBoxLayout()
        export_button = QPushButton(_("Экспорт справочника…"))
        export_button.clicked.connect(self._export)
        exchange_row.addWidget(export_button)
        import_button = QPushButton(_("Импорт справочника…"))
        import_button.clicked.connect(self._import_catalog)
        exchange_row.addWidget(import_button)
        exchange_row.addStretch(1)
        exchange_layout.addLayout(exchange_row)
        exchange_layout.addWidget(
            hint_label(
                _(
                    "При обмене передаются только ингредиенты и зелья: "
                    "инвентарь и журнал остаются вашими."
                )
            )
        )
        self.catalog_stats = QLabel()
        exchange_layout.addWidget(self.catalog_stats)

        box = self.layout_box()
        box.addWidget(page_heading(_("Настройки")))
        box.addWidget(kits_box)
        box.addWidget(profile_box)
        box.addWidget(data_box)
        box.addWidget(exchange_box)
        box.addStretch(1)

        self._loading = False
        bridge.settings_changed.connect(self.invalidate)
        bridge.catalog_changed.connect(self.invalidate)

    # ── отрисовка ─────────────────────────────────────────────────────────
    def refresh(self) -> None:
        super().refresh()
        self._loading = True
        settings = self.app.settings.settings
        for kit, check in self.kit_checks.items():
            check.setChecked(kit in settings.kits)
        self.character.setText(settings.character_name)
        index = self.theme.findData(settings.theme)
        self.theme.setCurrentIndex(max(0, index))
        self.data_path.setText(_("Папка данных: {path}").format(path=self.app.paths.root))
        self.settings_path.setText(_("Настройки: {path}").format(path=self.app.paths.settings_file))
        catalog = self.app.catalog.catalog
        known = sum(1 for p in catalog.potions if p.recipe is not None)
        self.catalog_stats.setText(
            _(
                "В справочнике: {ingredients} реагентов, {potions} зелий, "
                "{known} известных рецептов"
            ).format(
                ingredients=len(catalog.ingredients), potions=len(catalog.potions), known=known
            )
        )
        self._loading = False

    # ── сохранение ────────────────────────────────────────────────────────
    def _save_kits(self) -> None:
        if self._loading:
            return
        kits = tuple(kit for kit, check in self.kit_checks.items() if check.isChecked())
        self.app.settings.set_kits(kits)

    def _save_character(self) -> None:
        if not self._loading:
            self.app.settings.set_character_name(self.character.text().strip())

    def _save_theme(self) -> None:
        """Тема применяется сразу и запоминается в settings.toml (FR-9.5)."""
        if not self._loading:
            self.app.settings.set_theme(Theme(self.theme.currentData()))

    # ── действия ──────────────────────────────────────────────────────────
    def _open_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.app.paths.root)))

    def _backup(self) -> None:
        default = f"alchimist-backup-{datetime.now():%Y%m%d-%H%M}.zip"
        path, _filter = QFileDialog.getSaveFileName(
            self, _("Резервная копия"), default, "Zip (*.zip)"
        )
        if not path:
            return
        root = self.app.paths.root
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(root.rglob("*")):
                if file.is_file() and file.suffix not in {".tmp"}:
                    archive.write(file, file.relative_to(root))
        QMessageBox.information(self, _("Готово"), _("Копия сохранена: {path}").format(path=path))

    def _export(self) -> None:
        default = "alchimist-catalog.json"
        path, _filter = QFileDialog.getSaveFileName(
            self, _("Экспорт справочника"), default, "JSON (*.json)"
        )
        if not path:
            return
        self.app.exchange.export(Path(path), self.app.settings.settings.character_name)
        QMessageBox.information(
            self, _("Готово"), _("Справочник выгружен: {path}").format(path=path)
        )

    def _import_catalog(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, _("Импорт справочника"), "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            plan = self.app.exchange.plan(Path(path))
        except AlchimistError as exc:
            QMessageBox.warning(self, _("Не получилось"), describe(exc.message))
            return
        if not plan.has_changes:
            QMessageBox.information(self, _("Ничего нового"), _("Справочники совпадают полностью."))
            return
        dialog = MergeDialog(plan, self)
        if not dialog.exec():
            return
        messages = self.app.exchange.apply(plan, dialog.choices())
        self.app.brewing.invalidate()
        if messages:
            QMessageBox.warning(
                self,
                _("Справочник обновлён, но есть замечания"),
                "\n".join(describe(m) for m in messages[:20]),
            )
        else:
            QMessageBox.information(self, _("Готово"), _("Справочник обновлён."))
