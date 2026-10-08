"""Данные, которые едут вместе с приложением."""

from __future__ import annotations

from pathlib import Path

#: Справочник кампании: им заполняется пустой справочник при создании
#: персонажа (FR-14.2). Тот же файл служит живыми данными для тестов.
BUILTIN_CATALOG = Path(__file__).with_name("alchimist-catalog.json")
