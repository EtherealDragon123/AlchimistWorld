"""Тесты интерфейса идут только если PySide6 установлен и есть на чём рисовать."""

from __future__ import annotations

import gc
import os

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from alchimist.services import build_app


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def clean_widgets(qapp):
    """Не оставлять живых виджетов между тестами.

    Смена темы перекрашивает все виджеты приложения, и накопившиеся от прошлых
    тестов окна превращают пару сравнений цвета в десятки секунд.
    """
    yield
    for widget in list(qapp.topLevelWidgets()):
        widget.close()
        widget.deleteLater()
    qapp.processEvents()
    # deleteLater откладывает удаление до возврата в цикл событий, которого в
    # тестах нет: без этого виджеты копятся от теста к тесту.
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()


@pytest.fixture
def ui_app(tmp_path, catalog, qapp):
    service = build_app(tmp_path)
    service.catalog.replace_all(catalog)
    return service


@pytest.fixture
def window(ui_app, qapp):
    from alchimist.ui_qt.main_window import MainWindow

    win = MainWindow(ui_app)
    # Окно показывается, иначе страницы считают себя скрытыми и не перерисовываются.
    win.show()
    qapp.processEvents()
    yield win
    win.close()
