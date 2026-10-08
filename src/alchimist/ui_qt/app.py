"""Точка входа GUI (`alchimist-gui`)."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from alchimist.core.errors import AlchimistError
from alchimist.i18n import describe, set_language
from alchimist.services import build_app
from alchimist.ui_qt.resources import app_icon_path
from alchimist.ui_qt.theme import apply_theme

#: Имя файла `alchimist-world.desktop` без расширения (packaging/alchimist.desktop).
DESKTOP_FILE_NAME = "alchimist-world"


def _install_qt_translations(app: QApplication, language: str) -> list[QTranslator]:
    """Штатные строки Qt («OK», «Отмена») переводит сам Qt (03 §8)."""
    translators: list[QTranslator] = []
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    for name in ("qtbase", "qt"):
        translator = QTranslator(app)
        if translator.load(QLocale(language), name, "_", path):
            app.installTranslator(translator)
            translators.append(translator)
    return translators


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)
    app = QApplication(argv)
    app.setApplicationName("AlchimistWorld")
    app.setOrganizationName("AlchimistWorld")
    app.setApplicationDisplayName("AlchimistWorld")
    # Под Wayland это имя уходит композитору как app_id, и по нему рабочий стол
    # связывает окно с ярлыком. Без него Qt подставляет имя интерпретатора, и в
    # панели задач KDE или GNOME вместо значка приложения оказывается «python3».
    app.setDesktopFileName(DESKTOP_FILE_NAME)
    icon = app_icon_path()
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    data_dir = None
    if "--data" in argv:
        data_dir = Path(argv[argv.index("--data") + 1]).expanduser()

    try:
        services = build_app(data_dir)
    except AlchimistError as exc:
        QMessageBox.critical(None, "AlchimistWorld", describe(exc.message))
        return 1

    # Перевода пока нет (FR-11.4), и выбора языка в интерфейсе тоже: язык берётся из
    # ALCHIMIST_LANG, иначе русский. Сохранённый в settings.toml не применяется — у того,
    # кто успел выбрать English, кнопки Qt остались бы английскими без способа вернуть.
    language = set_language()
    app.setProperty("qt_translators", _install_qt_translations(app, language))
    apply_theme(app, services.settings.theme)

    from alchimist.ui_qt.main_window import MainWindow

    window = MainWindow(services)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
