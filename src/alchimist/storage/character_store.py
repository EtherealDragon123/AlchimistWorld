"""Персонажи: `character.json` в папке каждого профиля (03 §6.12)."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from alchimist.core.errors import Message, StorageError, WarningCode, warning
from alchimist.core.models import GM_ID, Character
from alchimist.storage.atomic import backup_path, write_atomic
from alchimist.storage.migrations import load_json
from alchimist.storage.paths import Paths
from alchimist.storage.serde import character_from_dict, character_to_dict, dumps

#: По этим файлам видно, что в папке профиля уже играли (до появления персонажей).
_PROFILE_DATA = ("inventory.json", "journal.json", "queue.json")


@dataclass(slots=True)
class CharacterStore:
    """Профиль в `paths` не важен: хранилище смотрит на все папки `profiles/` разом."""

    paths: Paths
    notices: list[Message] = field(default_factory=list)

    def _file(self, character_id: str) -> Path:
        return self.paths.for_profile(character_id).character_file

    def ids(self) -> list[str]:
        """Папки профилей, у которых есть персонаж."""
        root = self.paths.profiles_dir
        if not root.is_dir():
            return []
        return sorted(d.name for d in root.iterdir() if d.is_dir() and self._file(d.name).is_file())

    def legacy_ids(self) -> list[str]:
        """Профили, где уже играли, но персонажа ещё нет: их надо перенести (03 §6.12)."""
        root = self.paths.profiles_dir
        if not root.is_dir():
            return []
        return sorted(
            d.name
            for d in root.iterdir()
            if d.is_dir()
            and not self._file(d.name).exists()
            and any((d / name).is_file() for name in _PROFILE_DATA)
        )

    def taken_ids(self) -> set[str]:
        """Занятые имена папок, включая пустые и зарезервированное за GM."""
        root = self.paths.profiles_dir
        taken = {GM_ID}
        if root.is_dir():
            taken.update(d.name for d in root.iterdir())
        return taken

    def load(self, character_id: str) -> Character | None:
        path = self._file(character_id)
        if not path.exists():
            return None
        try:
            data = load_json(path, "character")
        except StorageError:
            # Как и с остальными файлами (NFR-8): при поломке берём резервную копию.
            backup = backup_path(path)
            if not backup.exists():
                raise
            data = load_json(backup, "character")
            self.notices.append(
                warning(WarningCode.STORAGE_RECOVERED_FROM_BAK, path=str(path), backup=str(backup))
            )
        return character_from_dict(data, character_id, str(path))

    def load_all(self) -> list[Character]:
        found = (self.load(character_id) for character_id in self.ids())
        return [character for character in found if character is not None]

    def save(self, character: Character) -> None:
        write_atomic(self._file(character.id), dumps(character_to_dict(character)))

    def delete(self, character_id: str) -> Path:
        """Папка профиля не стирается, а уезжает в `deleted-profiles/`: вдруг пригодится."""
        source = self.paths.for_profile(character_id).profile_dir
        target_root = self.paths.deleted_profiles_dir
        target_root.mkdir(parents=True, exist_ok=True)
        target = target_root / f"{character_id}-{datetime.now():%Y%m%d-%H%M%S}"
        shutil.move(str(source), str(target))
        return target
