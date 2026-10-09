"""Файлы сборки, которые проверяются без самой сборки (packaging/)."""

from __future__ import annotations

import struct
from pathlib import Path

PACKAGING = Path(__file__).resolve().parent.parent / "packaging"
PNG = b"\x89PNG\r\n\x1a\n"


def test_macos_icon_is_a_complete_icns() -> None:
    """Значок .app на macOS: без него в Finder виден значок PyInstaller.

    Файл собирает tools/icns.py; здесь проверяется, что он цел и в нём есть
    все размеры, вплоть до 1024 пикселей для Retina.
    """
    data = (PACKAGING / "icon.icns").read_bytes()
    assert data[:4] == b"icns"
    assert struct.unpack(">I", data[4:8])[0] == len(data)

    kinds = {}
    pos = 8
    while pos < len(data):
        kind = data[pos : pos + 4].decode("ascii")
        size = struct.unpack(">I", data[pos + 4 : pos + 8])[0]
        chunk = data[pos + 8 : pos + size]
        assert chunk.startswith(PNG), kind
        width, height = struct.unpack(">II", chunk[16:24])
        kinds[kind] = (width, height)
        pos += size
    assert pos == len(data)
    assert kinds["ic07"] == (128, 128)
    assert kinds["ic09"] == (512, 512)
    assert kinds["ic10"] == (1024, 1024)


def test_spec_gives_the_app_its_version_and_icon() -> None:
    """Без этого у .app «0.0.0» и чужой значок, а в свойствах .exe пусто."""
    spec = (PACKAGING / "alchimist.spec").read_text(encoding="utf-8")
    assert "version=VERSION" in spec
    assert '"icon.icns"' in spec
    assert '_common["version"] = _windows_version_info()' in spec
