"""Настройки в TOML (03 §6.7)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

import tomli_w

from alchimist.core.errors import ErrorCode, StorageError
from alchimist.core.models import Kit, Theme
from alchimist.storage.atomic import write_atomic
from alchimist.storage.paths import DEFAULT_PROFILE, Paths


@dataclass(frozen=True, slots=True)
class Settings:
    """Содержимое `settings.toml`: то, что общее для всех персонажей установки."""

    language: str = "ru"
    #: Тёмная тема — выбор по умолчанию при первом запуске.
    theme: Theme = Theme.DARK
    active_profile: str = DEFAULT_PROFILE
    schema_version: int = 1
    #: Наборы и имя раньше жили здесь, теперь — у персонажа (FR-14.5). Читаются
    #: только затем, чтобы перенести их в первого персонажа, и обратно не пишутся.
    legacy_kits: tuple[Kit, ...] = ()
    legacy_character_name: str = ""

    def with_(self, **changes: object) -> Settings:
        return replace(self, **changes)  # type: ignore[arg-type]


@dataclass(slots=True)
class SettingsStore:
    paths: Paths
    _cache: Settings | None = field(default=None, repr=False)

    @property
    def file(self) -> Path:
        return self.paths.settings_file

    def load(self) -> Settings:
        if not self.file.exists():
            self._cache = Settings()
            return self._cache
        try:
            data = tomllib.loads(self.file.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise StorageError(
                ErrorCode.STORAGE_CORRUPT, path=str(self.file), reason=str(exc)
            ) from exc
        kits: list[Kit] = []
        for raw in data.get("kits", []):
            try:
                kits.append(Kit(raw))
            except ValueError:
                continue
        theme = Theme.DARK
        raw_theme = data.get("theme")
        if raw_theme is not None:
            try:
                theme = Theme(str(raw_theme))
            except ValueError:
                theme = Theme.DARK
        self._cache = Settings(
            language=str(data.get("language", "ru")),
            theme=theme,
            active_profile=str(data.get("active_profile", DEFAULT_PROFILE)),
            schema_version=int(data.get("schema_version", 1)),
            legacy_kits=tuple(kits),
            legacy_character_name=str(data.get("character_name", "")),
        )
        return self._cache

    def save(self, settings: Settings) -> None:
        payload = {
            "schema_version": settings.schema_version,
            "language": settings.language,
            "theme": str(settings.theme.value),
            "active_profile": settings.active_profile,
        }
        write_atomic(self.file, tomli_w.dumps(payload))
        self._cache = settings
