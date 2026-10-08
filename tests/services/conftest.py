from __future__ import annotations

import pytest

from alchimist.core.models import Catalog, Kit
from alchimist.services import build_app
from alchimist.services.app import AppService


@pytest.fixture
def app(tmp_path, catalog: Catalog) -> AppService:
    service = build_app(tmp_path)
    service.catalog.replace_all(catalog)
    return service


@pytest.fixture
def play_as(app: AppService):
    """Сделать активным игрока, который знает все рецепты справочника.

    Наборы теперь у персонажа (FR-14.5), а знания тут не проверяются — поэтому
    знает он всё, как было до появления персонажей.
    """

    def play(name: str = "Гримли", kits: tuple[Kit, ...] = (Kit.ALCHEMIST,)):
        return app.create_character(name, kits, known=app.catalog.recipe_ids(), seed_catalog=False)

    return play
