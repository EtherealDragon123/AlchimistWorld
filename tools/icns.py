"""Собирает packaging/icon.icns для macOS из packaging/icon.svg.

    python tools/icns.py

Нужен `rsvg-convert` (пакет librsvg): им же из того же SVG сделан icon.png.
ICNS — это заголовок и подряд PNG-картинки разных размеров с четырёхбуквенными
типами; macOS сама берёт подходящую для Dock, Finder и Retina-экранов. Pillow или
`iconutil` для этого не нужны, поэтому собрать можно на любой ОС.
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "packaging" / "icon.svg"
ICNS = ROOT / "packaging" / "icon.icns"

#: Тип записи → сторона картинки в пикселях. Пары «@2x» (ic11–ic14, ic10) —
#: те же значки для Retina, поэтому одна сторона встречается под двумя типами.
ENTRIES = (
    ("icp4", 16),
    ("icp5", 32),
    ("icp6", 64),
    ("ic07", 128),
    ("ic08", 256),
    ("ic09", 512),
    ("ic10", 1024),
    ("ic11", 32),
    ("ic12", 64),
    ("ic13", 256),
    ("ic14", 512),
)


def render(size: int) -> bytes:
    result = subprocess.run(
        ["rsvg-convert", "-w", str(size), "-h", str(size), str(SVG)],
        check=True,
        capture_output=True,
    )
    return result.stdout


def build() -> bytes:
    pngs = {size: render(size) for size in sorted({size for _kind, size in ENTRIES})}
    body = b"".join(
        kind.encode("ascii") + struct.pack(">I", 8 + len(pngs[size])) + pngs[size]
        for kind, size in ENTRIES
    )
    return b"icns" + struct.pack(">I", 8 + len(body)) + body


def main() -> int:
    if shutil.which("rsvg-convert") is None:
        print("Нужен rsvg-convert (пакет librsvg).", file=sys.stderr)
        return 1
    ICNS.write_bytes(build())
    print(f"{ICNS.relative_to(ROOT)}: {ICNS.stat().st_size} байт, {len(ENTRIES)} картинок")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
