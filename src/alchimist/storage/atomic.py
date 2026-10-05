"""Атомарная запись файлов с резервной копией (NFR-3, 03 §6.2)."""

from __future__ import annotations

import os
import shutil
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path


def backup_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".bak")


@dataclass(slots=True)
class PendingWrite:
    """Подготовленная запись: текст уже на диске во временном файле.

    Варка меняет два файла (инвентарь и журнал): сначала готовятся оба `.tmp`,
    потом подряд два `os.replace` (03 §6.2).
    """

    path: Path
    tmp: Path

    def commit(self) -> None:
        """Заменяет целевой файл. Старый уходит в `.bak`."""
        if self.path.exists():
            with suppress(OSError):
                shutil.copy2(self.path, backup_path(self.path))
        os.replace(self.tmp, self.path)

    def abort(self) -> None:
        with suppress(OSError):
            self.tmp.unlink()


def prepare_write(path: Path, text: str) -> PendingWrite:
    """Пишет текст во временный файл рядом с целевым и делает fsync."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    return PendingWrite(path, tmp)


def write_atomic(path: Path, text: str) -> None:
    """Одиночная атомарная запись: tmp → fsync → копия в .bak → os.replace."""
    prepare_write(path, text).commit()


def commit_all(writes: list[PendingWrite]) -> None:
    """Подряд заменяет несколько подготовленных файлов."""
    for write in writes:
        write.commit()


def abort_all(writes: list[PendingWrite]) -> None:
    for write in writes:
        write.abort()
