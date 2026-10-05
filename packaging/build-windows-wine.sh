#!/usr/bin/env bash
# Сборка Windows-версии на Linux через Wine.
#
#     packaging/build-windows-wine.sh
#
# PyInstaller не умеет собирать под чужую ОС, поэтому внутри Wine ставится
# настоящий Windows-Python и запускается уже он. Получается честный PE-файл
# со всеми нужными DLL, включая библиотеки Visual C++ — отдельно ставить их
# не придётся.
#
# Оговорка: собранное так не проверялось на настоящей Windows. Если нужен
# результат с гарантией, соберите через GitHub Actions — там сборка идёт на
# настоящей windows-latest (см. .github/workflows/release.yml).
#
# Нужен пакет `wine` (на Arch/CachyOS: sudo pacman -S wine) и интернет.
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${ALCHIMIST_WINE_WORK:-$HOME/.cache/alchimist-wine-build}"
PYVER="${ALCHIMIST_WIN_PYTHON:-3.12.10}"
INSTALLER="python-${PYVER}-amd64.exe"
WPY='C:\Python312\python.exe'

export WINEPREFIX="$WORK/prefix"
export WINEARCH=win64
export WINEDEBUG=-all
# Без этого Wine предложит скачать Mono и Gecko, а они нам не нужны.
export WINEDLLOVERRIDES="mscoree,mshtml="

command -v wine >/dev/null || { echo "Нужен wine: sudo pacman -S wine"; exit 1; }
mkdir -p "$WORK"

# Каталоги перевода собираются окружением проекта: в системном Python нет babel.
if [ -x "$PROJECT/.venv/bin/python" ]; then
  PY="$PROJECT/.venv/bin/python"
else
  PY="$(command -v python3 || command -v python)"
fi

echo "=== 1/5 Префикс Wine: $WINEPREFIX ==="
wineboot -i >/dev/null 2>&1 || true
wineserver -w

echo "=== 2/5 Windows-Python $PYVER ==="
if [ ! -f "$WORK/$INSTALLER" ]; then
  curl -fSL --progress-bar -o "$WORK/$INSTALLER" \
       "https://www.python.org/ftp/python/${PYVER}/${INSTALLER}"
fi

if [ ! -f "$WINEPREFIX/drive_c/Python312/python.exe" ]; then
  echo "=== 3/5 Ставлю Python внутрь Wine ==="
  wine "$WORK/$INSTALLER" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 \
       Include_doc=0 Include_tcltk=0 Include_launcher=0 TargetDir='C:\Python312' \
       >/dev/null 2>&1 || true
  wineserver -w
else
  echo "=== 3/5 Python в Wine уже стоит ==="
fi
test -f "$WINEPREFIX/drive_c/Python312/python.exe" || {
  echo "ОШИБКА: Python внутри Wine не установился"; exit 1; }

echo "=== 4/5 Зависимости ==="
# Essentials вместо полного PySide6: нужны только QtCore/QtGui/QtWidgets,
# а полный пакет тянет ещё WebEngine и Quick — сотни лишних мегабайт.
wine "$WPY" -m pip install --disable-pip-version-check --no-warn-script-location -q \
     PySide6-Essentials platformdirs tomli-w babel pyinstaller

echo "=== 5/5 Сборка ==="
cd "$PROJECT"
"$PY" tools/i18n.py compile

rm -rf "$WORK/dist" "$WORK/build"
ALCHIMIST_ONEFILE=0 wine "$WPY" -m PyInstaller packaging/alchimist.spec --noconfirm \
     --distpath "$WORK/dist" --workpath "$WORK/build" --log-level WARN 2>&1 | grep -v MESA || true
ALCHIMIST_ONEFILE=1 wine "$WPY" -m PyInstaller packaging/alchimist.spec --noconfirm \
     --distpath "$WORK/dist-onefile" --workpath "$WORK/build-onefile" --log-level WARN 2>&1 \
     | grep -v MESA || true
wineserver -w

VERSION=$("$PY" -c "import re,pathlib;print(re.search(r'__version__ = \"(.*)\"', pathlib.Path('src/alchimist/__init__.py').read_text()).group(1))")
mkdir -p dist
(cd "$WORK/dist" && zip -qr "$PROJECT/dist/AlchimistWorld-$VERSION-windows.zip" AlchimistWorld)
cp "$WORK/dist-onefile/AlchimistWorld.exe" \
   "dist/AlchimistWorld-$VERSION-windows-одним-файлом.exe"

echo
echo "Готово:"
ls -lh dist/AlchimistWorld-"$VERSION"-windows* | awk '{print "  " $9 "  (" $5 ")"}'
