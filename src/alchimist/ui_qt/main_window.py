"""Главное окно: боковая панель слева, содержимое справа (02 §6)."""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QWidget,
)

from alchimist.core.models import KIT_NAMES_RU
from alchimist.i18n import _, describe
from alchimist.services.app import AppService
from alchimist.ui_qt.bridge import ServiceBridge
from alchimist.ui_qt.pages.almost import AlmostPage
from alchimist.ui_qt.pages.can_brew import CanBrewPage
from alchimist.ui_qt.pages.catalog import CatalogPage
from alchimist.ui_qt.pages.journal import JournalPage
from alchimist.ui_qt.pages.lab import LabPage
from alchimist.ui_qt.pages.potions import MyPotionsPage
from alchimist.ui_qt.pages.reagents import ReagentsPage
from alchimist.ui_qt.pages.settings import SettingsPage
from alchimist.ui_qt.theme import apply_theme, current_theme

#: Порядок страниц в боковой панели. None — разделитель.
PAGE_ORDER = [
    CanBrewPage,
    AlmostPage,
    LabPage,
    None,
    ReagentsPage,
    MyPotionsPage,
    None,
    CatalogPage,
    JournalPage,
    None,
    SettingsPage,
]


class MainWindow(QMainWindow):
    def __init__(self, app: AppService) -> None:
        super().__init__()
        self.app = app
        self.bridge = ServiceBridge(app.bus, self)
        self.setWindowTitle(self._title())
        self.resize(1180, 760)

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(200)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.stack = QStackedWidget()
        self.pages: list = []

        for index, page_class in enumerate(PAGE_ORDER):
            if page_class is None:
                separator = QListWidgetItem()
                separator.setFlags(Qt.ItemFlag.NoItemFlags)
                separator.setSizeHint(separator.sizeHint().boundedTo(separator.sizeHint()))
                separator.setText("─" * 12)
                self.nav.addItem(separator)
                continue
            page = page_class(app, self.bridge, self)
            self.pages.append(page)
            self.stack.addWidget(page)
            item = QListWidgetItem(f"{page_class.icon}  {_(page_class.title)}")
            item.setData(Qt.ItemDataRole.UserRole, self.stack.count() - 1)
            self.nav.addItem(item)
            del index

        self.nav.currentItemChanged.connect(self._navigate)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_box = QHBoxLayout(left)
        left_box.setContentsMargins(0, 0, 0, 0)
        left_box.addWidget(self.nav)
        splitter.addWidget(left)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(0, False)
        self.setCentralWidget(splitter)

        self.setStatusBar(QStatusBar())
        self._build_menu()
        self._restore_state()

        self.bridge.settings_changed.connect(self._on_settings_changed)
        self.bridge.settings_changed.connect(self._update_status)
        self.bridge.character_changed.connect(self._on_character_changed)
        self.bridge.inventory_changed.connect(self._update_status)
        self.bridge.catalog_changed.connect(self._update_status)
        self.bridge.queue_changed.connect(self._update_status)
        self._update_status()

        self._select_first()
        self._show_startup_notices()

    # ── навигация ─────────────────────────────────────────────────────────
    def _select_first(self) -> None:
        for row in range(self.nav.count()):
            item = self.nav.item(row)
            if item.data(Qt.ItemDataRole.UserRole) is not None:
                self.nav.setCurrentRow(row)
                return

    def _navigate(self, item: QListWidgetItem | None, _previous=None) -> None:
        if item is None:
            return
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is None:
            return
        self.stack.setCurrentIndex(index)
        page = self.stack.currentWidget()
        if hasattr(page, "activate"):
            page.activate()

    def go_to(self, page_class) -> None:
        for row in range(self.nav.count()):
            index = self.nav.item(row).data(Qt.ItemDataRole.UserRole)
            if index is None:
                continue
            if isinstance(self.stack.widget(index), page_class):
                self.nav.setCurrentRow(row)
                return

    # ── меню и горячие клавиши (NFR-9) ────────────────────────────────────
    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu(_("Файл"))
        reload_action = QAction(_("Перечитать файлы"), self)
        reload_action.setShortcut(QKeySequence.StandardKey.Refresh)
        reload_action.triggered.connect(self._reload)
        file_menu.addAction(reload_action)
        file_menu.addSeparator()
        quit_action = QAction(_("Выход"), self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = self.menuBar().addMenu(_("Переход"))
        for number, page_class in enumerate([p for p in PAGE_ORDER if p is not None], start=1):
            action = QAction(_(page_class.title), self)
            action.setShortcut(QKeySequence(f"Ctrl+{number}"))
            action.triggered.connect(lambda _c=False, cls=page_class: self.go_to(cls))
            view_menu.addAction(action)

        edit_menu = self.menuBar().addMenu(_("Правка"))
        undo_action = QAction(_("Отменить последнюю варку"), self)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(self._undo_last_brew)
        edit_menu.addAction(undo_action)

        help_menu = self.menuBar().addMenu(_("Справка"))
        about_action = QAction(_("О программе"), self)
        about_action.triggered.connect(self._about)
        help_menu.addAction(about_action)
        shortcuts_action = QAction(_("Горячие клавиши"), self)
        shortcuts_action.triggered.connect(self._shortcuts)
        help_menu.addAction(shortcuts_action)

    def _undo_last_brew(self) -> None:
        entry = self.app.brewing.last_brew()
        if entry is None:
            self.statusBar().showMessage(_("Отменять нечего"), 3000)
            return
        answer = QMessageBox.question(
            self,
            _("Отменить варку"),
            _("Вернуть реагенты последней варки и убрать полученное зелье?"),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        from alchimist.core.errors import AlchimistError

        try:
            self.app.brewing.undo_brew(entry.id)
        except AlchimistError as exc:
            QMessageBox.warning(self, _("Не получилось"), describe(exc.message))

    def _reload(self) -> None:
        self.app.reload()
        for page in self.pages:
            page.invalidate()
        self._update_status()
        self.statusBar().showMessage(_("Файлы перечитаны"), 3000)

    def _about(self) -> None:
        from alchimist import __version__

        QMessageBox.about(
            self,
            _("О программе"),
            _(
                "<h3>AlchimistWorld {version}</h3>"
                "<p>Помощник по homebrew-алхимии для D&D.</p>"
                "<p>Данные: {data}</p>"
            ).format(version=__version__, data=self.app.paths.root),
        )

    def _shortcuts(self) -> None:
        QMessageBox.information(
            self,
            _("Горячие клавиши"),
            _(
                "Ctrl+F — поиск на странице\n"
                "Ctrl+Enter — сварить\n"
                "Ctrl+1…Ctrl+8 — переход по страницам\n"
                "Ctrl+Z — отменить последнюю варку\n"
                "F5 — перечитать файлы"
            ),
        )

    # ── тема (FR-9.5) ─────────────────────────────────────────────────────
    def _on_settings_changed(self, *_args) -> None:
        """Тема применяется сразу, без перезапуска."""
        wanted = self.app.settings.theme
        if wanted == current_theme():
            return
        application = QApplication.instance()
        if application is not None:
            apply_theme(application, wanted)
        # Цвета строк списков проставляются при отрисовке, поэтому страницы
        # нужно перерисовать заново.
        for page in self.pages:
            page.invalidate()
        current = self.stack.currentWidget()
        if hasattr(current, "activate"):
            current.activate()

    # ── персонажи (FR-14.5) ───────────────────────────────────────────────
    def _on_character_changed(self, event=None) -> None:
        """Другой персонаж — другие инвентарь, журнал и права: перерисовать всё.

        Изученный рецепт или новые наборы меняют подбор и справочник, и страницам
        тоже проще пересчитаться целиком: это делается лениво, при показе.
        """
        for page in self.pages:
            page.invalidate()
        current = self.stack.currentWidget()
        if hasattr(current, "activate"):
            current.activate()
        self._update_status()
        if event is not None and getattr(event, "switched", False):
            active = self.app.characters.active
            if active is not None:
                self.statusBar().showMessage(_("Персонаж: {name}").format(name=active.name), 3000)

    # ── строка состояния ──────────────────────────────────────────────────
    def _update_status(self, *_args) -> None:
        kits = ", ".join(KIT_NAMES_RU[k] for k in self.app.characters.kits)
        reagents = sum(s.qty for s in self.app.inventory.inventory.reagents)
        potions = sum(s.qty for s in self.app.inventory.inventory.potions)
        message = _("Набор: {kits}   ·   реагентов: {reagents}   ·   зелий: {potions}").format(
            kits=kits, reagents=reagents, potions=potions
        )
        reserved = sum(self.app.brewing.reserved_quantities().values())
        if reserved:
            message += _("   ·   в очереди: {reserved}").format(reserved=reserved)
        self.statusBar().showMessage(message)
        self.setWindowTitle(self._title())

    def _title(self) -> str:
        active = self.app.characters.active
        return f"AlchimistWorld — {active.name}" if active else "AlchimistWorld"

    def _show_startup_notices(self) -> None:
        notices = self.app.startup_notices
        if notices:
            QMessageBox.warning(
                self,
                _("Данные загружены с замечаниями"),
                "\n".join(describe(m) for m in notices),
            )

    # ── состояние окна ────────────────────────────────────────────────────
    def _settings(self) -> QSettings:
        return QSettings("AlchimistWorld", "AlchimistWorld")

    def _restore_state(self) -> None:
        settings = self._settings()
        geometry = settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event) -> None:
        self._settings().setValue("geometry", self.saveGeometry())
        self.bridge.disconnect_bus()
        super().closeEvent(event)
