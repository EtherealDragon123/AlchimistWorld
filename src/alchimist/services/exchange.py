"""Экспорт и импорт справочника между игроками (FR-10.2–10.4, 03 §6.8)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from alchimist.core.errors import AlchimistError, ErrorCode, Message
from alchimist.core.models import Catalog, Ingredient, Potion, coerce_enum
from alchimist.core.rules import check_catalog
from alchimist.services.catalog import CatalogService
from alchimist.storage.atomic import write_atomic
from alchimist.storage.serde import (
    dumps,
    ingredient_from_dict,
    ingredient_to_dict,
    potion_from_dict,
    potion_to_dict,
)

EXCHANGE_FORMAT = "alchimist-catalog"
EXCHANGE_SCHEMA = 1


class MergeChoice(StrEnum):
    """Что делать с записью при слиянии (FR-10.3)."""

    KEEP_MINE = "mine"
    TAKE_THEIRS = "theirs"


@dataclass(frozen=True, slots=True)
class Difference:
    """Расхождение по одной записи: показывается игроку для выбора."""

    kind: str  # "ingredient" | "potion"
    id: str
    name: str
    mine: dict[str, Any] | None
    theirs: dict[str, Any] | None

    def changed_fields(self) -> list[str]:
        if self.mine is None or self.theirs is None:
            return []
        return sorted(
            key
            for key in set(self.mine) | set(self.theirs)
            if key != "updated_at" and self.mine.get(key) != self.theirs.get(key)
        )

    def updated_at(self) -> tuple[str | None, str | None]:
        mine = (self.mine or {}).get("updated_at")
        theirs = (self.theirs or {}).get("updated_at")
        return mine, theirs


@dataclass(slots=True)
class MergePlan:
    """Разбор чужого файла: что добавится и о чём надо спросить."""

    exported_by: str = ""
    exported_at: str = ""
    added: list[Difference] = field(default_factory=list)
    conflicts: list[Difference] = field(default_factory=list)
    identical: int = 0

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.conflicts)


@dataclass(slots=True)
class ExchangeService:
    catalog: CatalogService

    # ── FR-10.2 экспорт ───────────────────────────────────────────────────
    def export_payload(self, exported_by: str = "") -> str:
        data = {
            "format": EXCHANGE_FORMAT,
            "schema_version": EXCHANGE_SCHEMA,
            "exported_at": datetime.now().astimezone().isoformat(),
            "exported_by": exported_by,
            "ingredients": [
                ingredient_to_dict(i)
                for i in sorted(self.catalog.catalog.ingredients, key=lambda i: i.id)
            ],
            "potions": [
                potion_to_dict(p) for p in sorted(self.catalog.catalog.potions, key=lambda p: p.id)
            ],
        }
        return dumps(data)

    def export(self, path: Path, exported_by: str = "") -> Path:
        """Инвентарь и журнал не передаются (FR-10.4)."""
        write_atomic(Path(path), self.export_payload(exported_by))
        return Path(path)

    # ── FR-10.3 импорт со сравнением ──────────────────────────────────────
    def read_file(self, path: Path) -> dict[str, Any]:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AlchimistError(
                ErrorCode.EXCHANGE_BAD_FORMAT, path=str(path), reason=str(exc)
            ) from exc
        if not isinstance(data, dict) or data.get("format") != EXCHANGE_FORMAT:
            raise AlchimistError(ErrorCode.EXCHANGE_BAD_FORMAT, path=str(path))
        return data

    def plan(self, path: Path) -> MergePlan:
        """Сравнение по `id` (03 §6.8): новое, одинаковое, расходящееся."""
        data = self.read_file(path)
        plan = MergePlan(
            exported_by=str(data.get("exported_by", "")),
            exported_at=str(data.get("exported_at", "")),
        )
        mine_ingredients = {i.id: ingredient_to_dict(i) for i in self.catalog.catalog.ingredients}
        mine_potions = {p.id: potion_to_dict(p) for p in self.catalog.catalog.potions}

        for raw in data.get("ingredients", []):
            self._compare("ingredient", raw, mine_ingredients, plan)
        for raw in data.get("potions", []):
            self._compare("potion", raw, mine_potions, plan)
        return plan

    @staticmethod
    def _compare(kind: str, raw: dict, mine: dict[str, dict], plan: MergePlan) -> None:
        item_id = str(raw.get("id", ""))
        if not item_id:
            return
        name = str(raw.get("name", item_id))
        current = mine.get(item_id)
        if current is None:
            plan.added.append(Difference(kind, item_id, name, None, raw))
        elif _comparable(current) == _comparable(raw):
            plan.identical += 1
        else:
            plan.conflicts.append(Difference(kind, item_id, name, current, raw))

    def apply(
        self,
        plan: MergePlan,
        choices: dict[str, MergeChoice] | None = None,
        *,
        default: MergeChoice = MergeChoice.KEEP_MINE,
    ) -> list[Message]:
        """Применяет план. `choices` — решение по каждому расхождению (по id).

        Решения приходят из интерфейса, а Qt разворачивает `StrEnum` в обычную
        строку, поэтому значение приводится к типу здесь: сравнение `is` со
        строкой всегда ложно, и «взять чужое» молча превращалось бы в «оставить моё».
        """
        choices = {
            item_id: coerce_enum(MergeChoice, value, default)
            for item_id, value in (choices or {}).items()
        }
        ingredients = {i.id: i for i in self.catalog.catalog.ingredients}
        potions = {p.id: p for p in self.catalog.catalog.potions}

        for diff in plan.added:
            _install(diff, ingredients, potions)
        for diff in plan.conflicts:
            if choices.get(diff.id, default) is MergeChoice.TAKE_THEIRS:
                _install(diff, ingredients, potions)

        catalog = Catalog(list(ingredients.values()), list(potions.values()))
        self.catalog.replace_all(catalog)
        return check_catalog(catalog.ingredients, catalog.potions)


def _comparable(data: dict[str, Any]) -> dict[str, Any]:
    """Сравнение без `updated_at`: время правки само по себе расхождением не считается."""
    return {k: v for k, v in data.items() if k != "updated_at"}


def _install(
    diff: Difference, ingredients: dict[str, Ingredient], potions: dict[str, Potion]
) -> None:
    if diff.theirs is None:
        return
    if diff.kind == "ingredient":
        ingredients[diff.id] = ingredient_from_dict(diff.theirs)
    else:
        potions[diff.id] = potion_from_dict(diff.theirs)
