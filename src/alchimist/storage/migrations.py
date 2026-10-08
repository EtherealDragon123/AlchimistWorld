"""Миграции формата файлов (NFR-4, 03 §6.10).

`MIGRATIONS[kind]` — цепочка функций `v1 → v2 → …`. При загрузке файл с меньшей
`schema_version` прогоняется по цепочке, а исходник сохраняется как `файл.v1.bak`.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from alchimist.core.errors import ErrorCode, StorageError

#: Текущие версии схем.
CURRENT_VERSIONS: dict[str, int] = {
    "ingredients": 1,
    "potions": 1,
    "bases": 1,
    "inventory": 1,
    "journal": 3,
    "queue": 1,
    "settings": 1,
    "catalog-export": 1,
    "character": 1,
}

Migration = Callable[[dict[str, Any]], dict[str, Any]]


def _journal_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Правило о порциях и лишних эссенциях появилось позже журнала (П-8).

    В старых записях варка всегда была на одну порцию и ровно по рецепту,
    поэтому порций там одна, лишнего нет, а сложность неизвестна: тогда её
    не считали, и выдумывать задним числом нечего.
    """
    entries = []
    for entry in data.get("entries", []):
        if entry.get("type") == "brew":
            entry = {
                **entry,
                "portions": entry.get("portions", 1),
                "excess": entry.get("excess", {}),
                "difficulty": entry.get("difficulty"),
            }
        entries.append(entry)
    return {**data, "entries": entries}


def _journal_v2_to_v3(data: dict[str, Any]) -> dict[str, Any]:
    """Дистилляция — новый тип записи (П-9), старым записям он не нужен.

    Данные не меняются: версия поднята, чтобы приложение постарше не прочитало
    разбор на эссенции как варку — тип записи оно не знает и молча подставит
    свой, а это уже неправда в журнале.
    """
    return data


#: Цепочки миграций: MIGRATIONS["ingredients"][1] превращает v1 в v2.
MIGRATIONS: dict[str, dict[int, Migration]] = {
    "ingredients": {},
    "potions": {},
    "bases": {},
    "inventory": {},
    "journal": {1: _journal_v1_to_v2, 2: _journal_v2_to_v3},
    "queue": {},
    "settings": {},
    "catalog-export": {},
    "character": {},
}


def schema_version(data: dict[str, Any]) -> int:
    version = data.get("schema_version", 1)
    if not isinstance(version, int) or version < 1:
        raise StorageError(ErrorCode.STORAGE_UNKNOWN_SCHEMA, version=version)
    return version


def migrate(kind: str, data: dict[str, Any], *, source: Path | None = None) -> dict[str, Any]:
    """Прогоняет данные по цепочке до текущей версии.

    Перед первой миграцией исходник копируется в `файл.v<N>.bak`.
    """
    target = CURRENT_VERSIONS[kind]
    version = schema_version(data)
    if version > target:
        raise StorageError(
            ErrorCode.STORAGE_UNKNOWN_SCHEMA,
            path=str(source) if source else None,
            version=version,
            supported=target,
        )
    if version == target:
        return data

    if source is not None and source.exists():
        with suppress(OSError):
            shutil.copy2(source, source.with_suffix(f"{source.suffix}.v{version}.bak"))

    chain = MIGRATIONS[kind]
    while version < target:
        step = chain.get(version)
        if step is None:
            raise StorageError(
                ErrorCode.STORAGE_UNKNOWN_SCHEMA,
                path=str(source) if source else None,
                version=version,
                supported=target,
            )
        data = step(data)
        version += 1
        data["schema_version"] = version
    return data


def load_json(path: Path, kind: str) -> dict[str, Any]:
    """Читает JSON и приводит к текущей схеме.

    Повреждённый файл не роняет приложение (NFR-8): бросается StorageError
    с путём и номером строки, интерфейс предлагает откатиться на `.bak`.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise StorageError(ErrorCode.STORAGE_CORRUPT, path=str(path), reason=str(exc)) from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StorageError(
            ErrorCode.STORAGE_CORRUPT,
            path=str(path),
            line=exc.lineno,
            column=exc.colno,
            reason=exc.msg,
        ) from exc
    if not isinstance(data, dict):
        raise StorageError(ErrorCode.STORAGE_CORRUPT, path=str(path), reason="ожидался объект")
    return migrate(kind, data, source=path)
