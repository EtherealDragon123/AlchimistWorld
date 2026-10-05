"""Настройки приложения (FR-9.x)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from alchimist.core.models import Kit, Theme
from alchimist.services.events import EventBus, SettingsChanged
from alchimist.storage.paths import Paths
from alchimist.storage.settings_store import Settings, SettingsStore


@dataclass(slots=True)
class SettingsService:
    store: SettingsStore
    bus: EventBus
    _settings: Settings = field(default_factory=Settings)

    def __post_init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        self._settings = self.store.load()

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def kits(self) -> tuple[Kit, ...]:
        return self._settings.kits or (Kit.ALCHEMIST,)

    @property
    def theme(self) -> Theme:
        return self._settings.theme

    @property
    def paths(self) -> Paths:
        return self.store.paths

    def data_dir(self) -> Path:
        """Путь к папке данных для FR-9.4."""
        return self.store.paths.root

    def update(self, **changes: object) -> Settings:
        self._settings = self._settings.with_(**changes)
        self.store.save(self._settings)
        self.bus.publish(SettingsChanged())
        return self._settings

    def set_kits(self, kits: tuple[Kit, ...]) -> Settings:
        """FR-9.1: можно выбрать несколько наборов, пустой список — алхимик."""
        return self.update(kits=tuple(kits) or (Kit.ALCHEMIST,))

    def set_language(self, language: str) -> Settings:
        return self.update(language=language)

    def set_theme(self, theme: Theme) -> Settings:
        """FR-9.5: выбор темы запоминается между запусками."""
        return self.update(theme=Theme(theme))

    def set_character_name(self, name: str) -> Settings:
        return self.update(character_name=name)
