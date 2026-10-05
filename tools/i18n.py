#!/usr/bin/env python3
"""Сборка каталогов перевода (03 §8, FR-9.3, FR-11.4).

Команды:

    python tools/i18n.py extract      # обновить alchimist.pot
    python tools/i18n.py update       # влить изменения во все .po (и выровнять русский)
    python tools/i18n.py init en      # создать каталог нового языка
    python tools/i18n.py compile      # .po → .mo
    python tools/i18n.py sync         # msgstr = msgid в каталоге исходного языка
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALE_DIR = ROOT / "src" / "alchimist" / "i18n" / "locale"
POT = LOCALE_DIR / "alchimist.pot"
DOMAIN = "alchimist"

#: Язык исходных строк. В его каталоге перевод всегда совпадает с msgid, поэтому
#: он заполняется сам: иначе babel при обновлении подставляет в новые строки
#: ближайшие похожие («Разобрать» → «Сварить») и помечает их fuzzy.
SOURCE_LANGUAGE = "ru"


def run(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "babel.messages.frontend", *args], check=True, cwd=ROOT)


def extract() -> None:
    POT.parent.mkdir(parents=True, exist_ok=True)
    run(
        "extract",
        "-F",
        "babel.cfg",
        "-o",
        str(POT),
        "--project=AlchimistWorld",
        "--copyright-holder=AlchimistWorld",
        "--msgid-bugs-address=-",
        "src",
    )


def init(language: str) -> None:
    run("init", "-D", DOMAIN, "-i", str(POT), "-d", str(LOCALE_DIR), "-l", language)


def update() -> None:
    run("update", "-D", DOMAIN, "-i", str(POT), "-d", str(LOCALE_DIR))
    sync_source()


def sync_source() -> None:
    """Каталог исходного языка: msgstr = msgid, никаких fuzzy."""
    from babel.messages.pofile import read_po, write_po

    path = LOCALE_DIR / SOURCE_LANGUAGE / "LC_MESSAGES" / f"{DOMAIN}.po"
    if not path.exists():
        return
    with path.open("rb") as stream:
        catalog = read_po(stream, locale=SOURCE_LANGUAGE, domain=DOMAIN)
    changed = 0
    for message in catalog:
        if not message.id or message.pluralizable:
            continue
        if message.string != message.id or "fuzzy" in message.flags:
            message.string = message.id
            message.flags.discard("fuzzy")
            changed += 1
    with path.open("wb") as stream:
        write_po(stream, catalog, width=88)
    print(f"{SOURCE_LANGUAGE}: выровнено строк — {changed}")


def compile_all() -> None:
    # Без --use-fuzzy: догадка babel хуже, чем показать исходную строку.
    run("compile", "-D", DOMAIN, "-d", str(LOCALE_DIR))


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "extract"
    match command:
        case "extract":
            extract()
        case "init":
            init(sys.argv[2])
        case "update":
            extract()
            update()
        case "compile":
            compile_all()
        case "sync":
            sync_source()
        case _:
            print(__doc__)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
