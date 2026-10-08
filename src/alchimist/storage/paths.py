"""Где лежат файлы данных (03 §6.1)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import platformdirs

APP_NAME = "AlchimistWorld"

#: Переопределяет папку данных: для тестов и «портативного» режима.
DATA_DIR_ENV = "ALCHIMIST_DATA_DIR"
#: Отдельно переопределяет settings.toml (обычно не нужен).
CONFIG_DIR_ENV = "ALCHIMIST_CONFIG_DIR"

DEFAULT_PROFILE = "default"


def data_dir() -> Path:
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return Path(platformdirs.user_data_dir(APP_NAME, appauthor=False, roaming=False))


def config_dir() -> Path:
    override = os.environ.get(CONFIG_DIR_ENV)
    if override:
        return Path(override).expanduser()
    override_data = os.environ.get(DATA_DIR_ENV)
    if override_data:
        # В портативном режиме настройки лежат рядом с данными.
        return Path(override_data).expanduser()
    return Path(platformdirs.user_config_dir(APP_NAME, appauthor=False, roaming=False))


@dataclass(frozen=True, slots=True)
class Paths:
    """Пути ко всем файлам приложения."""

    root: Path
    config: Path
    profile: str = DEFAULT_PROFILE

    @classmethod
    def resolve(cls, profile: str = DEFAULT_PROFILE) -> Paths:
        return cls(root=data_dir(), config=config_dir(), profile=profile)

    @classmethod
    def at(cls, root: Path, profile: str = DEFAULT_PROFILE) -> Paths:
        """Явный корень: удобно в тестах и для «портативного» режима."""
        return cls(root=Path(root), config=Path(root), profile=profile)

    # ── каталог партии ───────────────────────────────────────────────────
    @property
    def catalog_dir(self) -> Path:
        return self.root / "catalog"

    @property
    def ingredients_file(self) -> Path:
        return self.catalog_dir / "ingredients.json"

    @property
    def potions_file(self) -> Path:
        return self.catalog_dir / "potions.json"

    @property
    def bases_file(self) -> Path:
        """На будущее: особые основы (П-4.4, FR-11.1)."""
        return self.catalog_dir / "bases.json"

    # ── профиль персонажа ────────────────────────────────────────────────
    @property
    def profiles_dir(self) -> Path:
        return self.root / "profiles"

    @property
    def profile_dir(self) -> Path:
        return self.profiles_dir / self.profile

    @property
    def inventory_file(self) -> Path:
        return self.profile_dir / "inventory.json"

    @property
    def journal_file(self) -> Path:
        return self.profile_dir / "journal.json"

    @property
    def character_file(self) -> Path:
        """Имя, роль, наборы и изученные рецепты персонажа (FR-14.5)."""
        return self.profile_dir / "character.json"

    @property
    def deleted_profiles_dir(self) -> Path:
        """Куда уезжает удалённый персонаж: так его ещё можно вернуть руками."""
        return self.root / "deleted-profiles"

    @property
    def queue_file(self) -> Path:
        """Очередь варок: план игрока, а не факт (FR-12.1)."""
        return self.profile_dir / "queue.json"

    # ── настройки ────────────────────────────────────────────────────────
    @property
    def settings_file(self) -> Path:
        return self.config / "settings.toml"

    def for_profile(self, profile: str) -> Paths:
        return Paths(self.root, self.config, profile)

    def ensure(self, *, profile: bool = True) -> Paths:
        """Создаёт недостающие папки.

        Папку профиля — только когда за ней есть персонаж: пустая `profiles/default/`
        на свежей установке потом путалась бы с профилем, где уже играли.
        """
        self.catalog_dir.mkdir(parents=True, exist_ok=True)
        if profile:
            self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.config.mkdir(parents=True, exist_ok=True)
        return self
