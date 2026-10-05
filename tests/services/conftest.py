from __future__ import annotations

import pytest

from alchimist.core.models import Catalog
from alchimist.services import build_app
from alchimist.services.app import AppService


@pytest.fixture
def app(tmp_path, catalog: Catalog) -> AppService:
    service = build_app(tmp_path)
    service.catalog.replace_all(catalog)
    return service
