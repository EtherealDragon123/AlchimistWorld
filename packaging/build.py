#!/usr/bin/env python3
"""Сборка самодостаточного пакета для текущей ОС (03 §10).

    python packaging/build.py              # папка + архив
    python packaging/build.py --onefile    # плюс один файл, который просто отправить
    python packaging/build.py --no-archive # только папка, без упаковки

PyInstaller собирает **только под ту ОС, на которой запущен**. Windows-сборку
делает GitHub Actions по тегу `v*` (.github/workflows/release.yml) либо
`packaging/build-windows-wine.sh` — он поднимает Windows-Python внутри Wine.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging" / "alchimist.spec"
DIST = ROOT / "dist"
BUILD = ROOT / "build"

#: Как называется готовый архив на каждой ОС.
PLATFORM_TAG = {"Linux": "linux", "Windows": "windows", "Darwin": "macos"}


def version() -> str:
    text = (ROOT / "src" / "alchimist" / "__init__.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("__version__"):
            return line.split("=")[1].strip().strip('"')
    return "0.0.0"


def run(*args: str, env: dict[str, str] | None = None) -> None:
    print(f"→ {' '.join(args)}")
    subprocess.run(args, check=True, cwd=ROOT, env=env)


def compile_translations() -> None:
    """Без собранных `.mo` интерфейс останется на исходных строках (03 §8)."""
    run(sys.executable, str(ROOT / "tools" / "i18n.py"), "compile")


def build(onefile: bool) -> Path:
    """Собирает вариант из одного файла в отдельную папку.

    На Linux и macOS одиночный файл называется так же, как папка обычной сборки,
    и без отдельного `--distpath` вторая сборка затирает первую.
    """
    env = dict(os.environ)
    env["ALCHIMIST_ONEFILE"] = "1" if onefile else "0"
    dist = DIST / "onefile" if onefile else DIST
    run(
        sys.executable,
        "-m",
        "PyInstaller",
        str(SPEC),
        "--noconfirm",
        "--distpath",
        str(dist),
        "--workpath",
        str(BUILD / ("onefile" if onefile else "onedir")),
        "--log-level",
        "WARN",
        env=env,
    )
    name = "AlchimistWorld.exe" if sys.platform == "win32" else "AlchimistWorld"
    return dist / name if onefile else dist / "AlchimistWorld"


def archive(target: Path, tag: str) -> Path:
    """Zip под Windows, tar.gz на остальных: так привычнее на каждой стороне."""
    base = DIST / f"AlchimistWorld-{version()}-{tag}"
    if sys.platform == "win32":
        # Не with_suffix: тот принял бы «.0-windows» за расширение и отрезал его.
        result = Path(f"{base}.zip")
        with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in sorted(target.rglob("*")):
                if file.is_file():
                    zf.write(file, Path(target.name) / file.relative_to(target))
    else:
        result = Path(f"{base}.tar.gz")
        with tarfile.open(result, "w:gz") as tf:
            tf.add(target, arcname=target.name)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--onefile", action="store_true", help="собрать ещё и вариант из одного файла"
    )
    parser.add_argument("--no-archive", action="store_true", help="не паковать результат")
    parser.add_argument("--clean", action="store_true", help="снести dist/ и build/ перед сборкой")
    args = parser.parse_args()

    tag = PLATFORM_TAG.get(platform.system(), platform.system().lower())
    print(f"Сборка AlchimistWorld {version()} для {platform.system()} ({platform.machine()})\n")

    if args.clean:
        for folder in (DIST, BUILD):
            shutil.rmtree(folder, ignore_errors=True)

    compile_translations()

    folder = build(onefile=False)
    print(f"\nПапка: {folder}")
    if not args.no_archive:
        print(f"Архив: {archive(folder, tag)}")

    if args.onefile:
        single = build(onefile=True)
        suffix = ".exe" if sys.platform == "win32" else ""
        final = DIST / f"AlchimistWorld-{version()}-{tag}{suffix}"
        final.unlink(missing_ok=True)
        shutil.move(str(single), final)
        shutil.rmtree(DIST / "onefile", ignore_errors=True)
        final.chmod(0o755)
        print(f"Один файл: {final}")

    print("\nГотово.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
