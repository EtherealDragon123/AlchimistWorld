"""Страница «Настройки»: персонажи и наборы, тема, данные, справочник (FR-9, FR-10, FR-14)."""

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
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from alchimist.core.errors import AlchimistError
from alchimist.core.models import KIT_NAMES_RU, THEME_NAMES_RU, Kit, Theme
from alchimist.i18n import _, describe
from alchimist.ui_qt.dialogs.character_dialog import CharacterDialog
from alchimist.ui_qt.dialogs.merge_dialog import MergeDialog
from alchimist.ui_qt.pages.base import Page
from alchimist.ui_qt.widgets.common import hint_label, page_heading


class SettingsPage(Page):
    title = "Настройки"
    icon = "⚙"
    scrollable = True

    def __init__(self, app, bridge, parent: QWidget | None = None) -> None:
        super().__init__(app, bridge, parent)

        # ── персонаж и его наборы (FR-9.1, FR-14.5) ───────────────────────
        # Наборы принадлежат персонажу, поэтому живут в одном блоке с ним.
        character_box = QGroupBox(_("Персонаж"))
        character_layout = QVBoxLayout(character_box)

        row = QHBoxLayout()
        row.addWidget(QLabel(_("Активный персонаж")))
        self.character_combo = QComboBox()
        self.character_combo.setMinimumWidth(220)
        self.character_combo.currentIndexChanged.connect(self._switch)
        row.addWidget(self.character_combo, 1)
        self.new_button = QPushButton(_("Новый…"))
        self.new_button.clicked.connect(self._new_character)
        self.rename_button = QPushButton(_("Переименовать…"))
        self.rename_button.clicked.connect(self._rename_character)
        self.delete_button = QPushButton(_("Удалить…"))
        self.delete_button.clicked.connect(self._delete_character)
        for button in (self.new_button, self.rename_button, self.delete_button):
            row.addWidget(button)
        character_layout.addLayout(row)
        character_layout.addWidget(
            hint_label(
                _(
                    "У каждого персонажа свои наборы, реагенты, зелья, журнал и изученные "
                    "рецепты. Справочник общий."
                )
            )
        )
        self.role_label = hint_label()
        character_layout.addWidget(self.role_label)

        kits_label = QLabel(_("Наборы инструментов"))
        kits_label.setObjectName("subheading")
        character_layout.addWidget(kits_label)
        self.kit_checks: dict[Kit, QCheckBox] = {}
        for kit in Kit:
            check = QCheckBox(KIT_NAMES_RU[kit])
            check.toggled.connect(lambda _v: self._save_kits())
            self.kit_checks[kit] = check
            character_layout.addWidget(check)
        character_layout.addWidget(
            hint_label(
                _(
                    "Можно выбрать несколько. Вариант доступен, если его разрешает хотя бы один "
                    "набор, но смешивать права разных наборов в одной варке нельзя (П-6.3)."
                )
            )
        )

        # ── оформление (FR-9.5) ───────────────────────────────────────────
        # Тема общая для всех персонажей установки.
        look_box = QGroupBox(_("Оформление"))
        look_form = QFormLayout(look_box)
        self.theme = QComboBox()
        for theme in Theme:
            self.theme.addItem(THEME_NAMES_RU[theme], theme)
        self.theme.currentIndexChanged.connect(self._save_theme)
        look_form.addRow(_("Тема оформления"), self.theme)
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
        # Выгружает только GM: в файле все рецепты разом (FR-14.6).
        self.export_button = QPushButton(_("Экспорт справочника…"))
        self.export_button.clicked.connect(self._export)
        exchange_row.addWidget(self.export_button)
        import_button = QPushButton(_("Импорт справочника…"))
        import_button.clicked.connect(self._import_catalog)
        exchange_row.addWidget(import_button)
        exchange_row.addStretch(1)
        exchange_layout.addLayout(exchange_row)
        exchange_layout.addWidget(
            hint_label(
                _(
                    "При обмене передаются только ингредиенты и зелья: "
                    "инвентарь, журнал и изученные рецепты остаются вашими."
                )
            )
        )
        self.catalog_stats = QLabel()
        exchange_layout.addWidget(self.catalog_stats)

        box = self.layout_box()
        box.addWidget(page_heading(_("Настройки")))
        box.addWidget(character_box)
        box.addWidget(look_box)
        box.addWidget(data_box)
        box.addWidget(exchange_box)
        box.addStretch(1)

        self._loading = False
        bridge.settings_changed.connect(self.invalidate)
        bridge.catalog_changed.connect(self.invalidate)
        bridge.character_changed.connect(self.invalidate)

    # ── отрисовка ─────────────────────────────────────────────────────────
    def refresh(self) -> None:
        super().refresh()
        self._loading = True
        characters = self.app.characters.characters()
        active = self.app.characters.active

        self.character_combo.clear()
        for character in characters:
            self.character_combo.addItem(character.name, character.id)
        if active is not None:
            self.character_combo.setCurrentIndex(max(0, self.character_combo.findData(active.id)))
        self.rename_button.setEnabled(active is not None and not active.is_gm)
        self.delete_button.setEnabled(active is not None and len(characters) > 1)
        if active is not None and active.is_gm:
            self.role_label.setText(_("Это GM: знает все рецепты и один может менять справочник."))
        else:
            self.role_label.setText("")
        self.role_label.setVisible(bool(self.role_label.text()))

        kits = self.app.characters.kits
        for kit, check in self.kit_checks.items():
            check.setChecked(kit in kits)
            check.setEnabled(active is not None)

        index = self.theme.findData(self.app.settings.theme)
        self.theme.setCurrentIndex(max(0, index))
        self.data_path.setText(_("Папка данных: {path}").format(path=self.app.paths.root))
        self.settings_path.setText(_("Настройки: {path}").format(path=self.app.paths.settings_file))

        self.export_button.setVisible(self.app.can_edit_catalog)
        catalog = self.app.catalog.catalog
        recipes = self.app.catalog.recipe_ids()
        if active is None or active.is_gm:
            known = len(recipes)
        else:
            known = len(active.known_recipes & recipes)
        known_reagents = sum(
            1 for i in catalog.ingredients if self.app.catalog.knows_ingredient(i.id)
        )
        self.catalog_stats.setText(
            _(
                "В справочнике: {ingredients} реагентов, {potions} зелий, {recipes} рецептов. "
                "Изучено: {known} рецептов и {known_reagents} реагентов."
            ).format(
                ingredients=len(catalog.ingredients),
                potions=len(catalog.potions),
                recipes=len(recipes),
                known=known,
                known_reagents=known_reagents,
            )
        )
        self._loading = False

    # ── персонажи ─────────────────────────────────────────────────────────
    def _switch(self) -> None:
        if self._loading:
            return
        character_id = self.character_combo.currentData()
        active = self.app.characters.active
        if character_id and (active is None or active.id != character_id):
            self.app.switch_character(character_id)

    def _new_character(self) -> None:
        dialog = CharacterDialog(
            lambda name, kits: self.app.create_character(name, kits), self.window()
        )
        dialog.exec()

    def _rename_character(self) -> None:
        active = self.app.characters.active
        if active is None:
            return
        name, ok = QInputDialog.getText(
            self, _("Переименовать персонажа"), _("Новое имя"), text=active.name
        )
        if not ok or not name.strip():
            return
        try:
            self.app.rename_character(active.id, name)
        except AlchimistError as exc:
            QMessageBox.warning(self, _("Не получилось"), describe(exc.message))

    def _delete_character(self) -> None:
        active = self.app.characters.active
        if active is None:
            return
        answer = QMessageBox.question(
            self,
            _("Удалить персонажа"),
            _(
                "Удалить «{name}» вместе с его реагентами, зельями, журналом и изученными "
                "рецептами?\n\nФайлы не стираются насовсем, а переносятся в папку "
                "deleted-profiles внутри папки данных."
            ).format(name=active.name),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.app.delete_character(active.id)
        except AlchimistError as exc:
            QMessageBox.warning(self, _("Не получилось"), describe(exc.message))

    # ── сохранение ────────────────────────────────────────────────────────
    def _save_kits(self) -> None:
        if self._loading or self.app.characters.active is None:
            return
        kits = tuple(kit for kit, check in self.kit_checks.items() if check.isChecked())
        self.app.set_kits(kits)

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
        try:
            self.app.export_catalog(Path(path))
        except AlchimistError as exc:
            QMessageBox.warning(self, _("Не получилось"), describe(exc.message))
            return
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
