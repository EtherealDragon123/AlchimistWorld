# PyInstaller: папка с исполняемым файлом, на macOS — ещё и .app (03 §10).
#
#     pyinstaller packaging/alchimist.spec --noconfirm
#
# Собирать надо на той же ОС, под которую нужен результат: PyInstaller не умеет
# собирать под чужую систему. Под Windows и macOS это делает GitHub Actions
# (.github/workflows/release.yml), локально — packaging/build.py.

import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"


def _version() -> str:
    """Версия из src/alchimist/__init__.py — так же её читает build.py."""
    text = (SRC / "alchimist" / "__init__.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("__version__"):
            return line.split("=")[1].strip().strip('"')
    raise SystemExit("В src/alchimist/__init__.py нет __version__")


VERSION = _version()

#: ALCHIMIST_ONEFILE=1 собирает всё в один файл: его удобно просто отправить,
#: но при каждом запуске он распаковывается во временную папку и стартует дольше.
ONEFILE = os.environ.get("ALCHIMIST_ONEFILE") == "1"

#: Qt тянет за собой Qml, виртуальную клавиатуру и просмотр PDF — приложению
#: на QtWidgets они не нужны и занимают заметную часть сборки.
UNUSED_QT = (
    "Qt6Qml",
    "Qt6Quick",
    "Qt6QuickWidgets",
    "Qt6QuickControls2",
    "Qt6VirtualKeyboard",
    "Qt6Pdf",
    "Qt63D",
    "Qt6Charts",
    "Qt6DataVisualization",
    "Qt6Multimedia",
    "Qt6WebEngine",
    "Qt6Designer",
    "Qt6Test",
    "Qt6Sql",
)

#: Каталоги плагинов Qt, без которых приложение обходится.
UNUSED_PLUGIN_DIRS = (
    "qml/",
    "plugins/virtualkeyboard",
    "plugins/qmltooling",
    "plugins/sqldrivers",
    "plugins/multimedia",
    "plugins/designer",
    "plugins/renderers",
    "plugins/sceneparsers",
    "plugins/geometryloaders",
)

#: Тема оформления GTK не нужна: интерфейс всегда рисуется стилем Fusion (FR-9.5),
#: а плагин тянет за собой сам GTK и вторую копию данных ICU — десятки мегабайт.
UNUSED_PLUGINS = (
    "platformthemes/libqgtk3",
    "platformthemes/qgtk3",
)


def _windows_version_info():
    """Вкладка «Подробно» в свойствах .exe: версия, название и описание.

    Без неё там пусто, а «Описание файла» Windows показывает, например, в
    диспетчере задач. Числовая версия — четыре числа, «2.5.0» → 2.5.0.0.
    """
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    digits = []
    for part in VERSION.split(".")[:4]:
        number = "".join(ch for ch in part if ch.isdigit()) or "0"
        digits.append(int(number))
    numbers = tuple(digits + [0] * (4 - len(digits)))
    strings = {
        "FileDescription": "AlchimistWorld",
        "FileVersion": VERSION,
        "InternalName": "AlchimistWorld",
        "LegalCopyright": "MIT",
        "OriginalFilename": "AlchimistWorld.exe",
        "ProductName": "AlchimistWorld",
        "ProductVersion": VERSION,
    }
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
        kids=[
            # 0419 — русский, 04B0 — Юникод (кодовая страница 1200).
            StringFileInfo(
                [StringTable("041904B0", [StringStruct(k, v) for k, v in strings.items()])]
            ),
            VarFileInfo([VarStruct("Translation", [0x0419, 1200])]),
        ],
    )


def _drop(entries, patterns):
    """Убирает из списка PyInstaller всё, чей путь содержит одну из подстрок."""
    kept = []
    for entry in entries:
        name = entry[0].replace("\\", "/")
        source = (entry[1] or "").replace("\\", "/")
        if any(p in name or p in source for p in patterns):
            continue
        kept.append(entry)
    return kept


a = Analysis(
    [str(SRC / "alchimist" / "ui_qt" / "app.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[
        # Скомпилированные каталоги перевода нужны в сборке (03 §8).
        (str(SRC / "alchimist" / "i18n" / "locale"), "alchimist/i18n/locale"),
        # Значок окна и панели задач.
        (str(SRC / "alchimist" / "ui_qt" / "resources"), "alchimist/ui_qt/resources"),
        # Встроенный справочник: им заполняется справочник нового персонажа (FR-14.2).
        (str(SRC / "alchimist" / "data" / "alchimist-catalog.json"), "alchimist/data"),
    ],
    # Окно и страницы подключаются по строке внутри main(), сам PyInstaller их не видит.
    hiddenimports=["alchimist.ui_qt.main_window"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "pydoc_data",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore",
        "PySide6.QtCharts",
        "PySide6.QtMultimedia",
        "PySide6.QtSql",
        "PySide6.QtTest",
        "PySide6.QtDesigner",
    ],
)

a.binaries = _drop(a.binaries, UNUSED_QT + UNUSED_PLUGINS + UNUSED_PLUGIN_DIRS)
a.datas = _drop(a.datas, UNUSED_PLUGIN_DIRS + ("translations/qtwebengine",))

pyz = PYZ(a.pure, a.zipped_data)

_icon = ROOT / "packaging" / ("icon.ico" if sys.platform == "win32" else "icon.png")
_common = {
    "name": "AlchimistWorld",
    # Без консольного окна: на Windows иначе рядом открывается чёрный терминал.
    "console": False,
    "disable_windowed_traceback": False,
    "icon": str(_icon) if _icon.exists() else None,
}
if sys.platform == "win32":
    # Только для Windows: на других ОС PyInstaller эту настройку игнорирует с предупреждением.
    _common["version"] = _windows_version_info()

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        strip=False,
        upx=False,
        runtime_tmpdir=None,
        **_common,
    )
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **_common)
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        name="AlchimistWorld",
    )

    if sys.platform == "darwin":
        # Иконку и версию .app берёт не из EXE: без них в Finder и «Об этой программе»
        # видны значок PyInstaller и «0.0.0». Иконка собрана из icon.svg (tools/icns.py).
        app = BUNDLE(
            coll,
            name="AlchimistWorld.app",
            icon=str(ROOT / "packaging" / "icon.icns"),
            version=VERSION,
            bundle_identifier="world.alchimist.app",
            info_plist={
                "NSHighResolutionCapable": True,
                "LSMinimumSystemVersion": "12.0",
                "CFBundleVersion": VERSION,
            },
        )
