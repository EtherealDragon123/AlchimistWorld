"""Справочник: реагенты, зелья, рецепты (FR-1.x, FR-2.x)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime

from alchimist.core.elements import ElementVector
from alchimist.core.errors import AlchimistError, ErrorCode, Message
from alchimist.core.ids import normalize_name, unique_id
from alchimist.core.models import (
    BASE_ORDER,
    BaseKey,
    Catalog,
    Ingredient,
    IngredientCategory,
    Potion,
    Recipe,
)
from alchimist.core.rules import (
    RecipeKey,
    build_recipe_index,
    check_ingredient,
    check_recipe,
)
from alchimist.services.events import CatalogChanged, EventBus
from alchimist.storage.repository import CatalogRepository


def _now() -> datetime:
    return datetime.now().astimezone()


@dataclass(slots=True)
class CatalogService:
    """Единственный владелец справочника в памяти.

    Держит его целиком: реагентов и зелий сотни, это микросекунды на перестройку
    индексов и мгновенный отклик интерфейса (03 §5.5).
    """

    repo: CatalogRepository
    bus: EventBus
    #: Какие рецепты знает активный персонаж; None — все (GM или персонажа нет).
    #: Чтение зелий через `potions()`, `potion()` и `potion_map()` показывает только
    #: их: у неизученного рецепт скрыт, и подбор его не видит (FR-14.3, FR-14.8).
    #: Сам справочник целиком — в `catalog`: им пользуются обмен и правка GM.
    known_recipes: Callable[[], frozenset[str] | None] | None = None
    _catalog: Catalog = field(default_factory=Catalog)
    _index: dict[RecipeKey, set[str]] = field(default_factory=dict)
    _notices: list[Message] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.reload()

    # ── чтение ────────────────────────────────────────────────────────────
    def reload(self) -> None:
        self._catalog = self.repo.load()
        self._notices = list(getattr(self.repo, "notices", []) or [])
        self._reindex()

    def _reindex(self) -> None:
        self._index = build_recipe_index(self._catalog.potions)

    @property
    def notices(self) -> list[Message]:
        """Что случилось при загрузке (например откат на `.bak`)."""
        return list(self._notices)

    @property
    def catalog(self) -> Catalog:
        return self._catalog

    @property
    def recipe_index(self) -> dict[RecipeKey, set[str]]:
        return self._index

    def ingredients(self, *, include_hidden: bool = False) -> list[Ingredient]:
        items = self._catalog.ingredients
        if not include_hidden:
            items = [i for i in items if not i.hidden]
        return sorted(items, key=lambda i: i.name.casefold())

    def potions(self, *, include_hidden: bool = False) -> list[Potion]:
        items = self._catalog.potions
        if not include_hidden:
            items = [p for p in items if not p.hidden]
        known = self._known()
        return sorted(
            (self._view(p, known) for p in items), key=lambda p: (p.rarity, p.name.casefold())
        )

    def ingredient_map(self) -> dict[str, Ingredient]:
        return {i.id: i for i in self._catalog.ingredients}

    def potion_map(self) -> dict[str, Potion]:
        known = self._known()
        return {p.id: self._view(p, known) for p in self._catalog.potions}

    def ingredient(self, ingredient_id: str) -> Ingredient:
        item = self._catalog.ingredient_by_id(ingredient_id)
        if item is None:
            raise AlchimistError(ErrorCode.NOT_FOUND, id=ingredient_id)
        return item

    def potion(self, potion_id: str) -> Potion:
        return self._view(self.raw_potion(potion_id), self._known())

    def raw_potion(self, potion_id: str) -> Potion:
        """Зелье как есть, с рецептом, даже если персонаж его не изучил."""
        item = self._catalog.potion_by_id(potion_id)
        if item is None:
            raise AlchimistError(ErrorCode.NOT_FOUND, id=potion_id)
        return item

    # ── знание рецептов (FR-14.3) ─────────────────────────────────────────
    def _known(self) -> frozenset[str] | None:
        return self.known_recipes() if self.known_recipes is not None else None

    @staticmethod
    def _view(potion: Potion, known: frozenset[str] | None) -> Potion:
        """Неизученный рецепт выглядит как неизвестный: подбор его не видит.

        Примечание к рецепту прячется вместе с ним — там бывают подсказки. У зелья
        без рецепта примечание общее для всех (Бармаглот) и остаётся на месте.
        """
        if known is None or potion.recipe is None or potion.id in known:
            return potion
        return potion.copy(recipe=None, recipe_note=None)

    def has_recipe(self, potion_id: str) -> bool:
        """Есть ли рецепт в самом справочнике: только такой и можно изучить."""
        return self.raw_potion(potion_id).recipe is not None

    def recipe_ids(self) -> frozenset[str]:
        """Все зелья, у которых в справочнике записан рецепт."""
        return frozenset(p.id for p in self._catalog.potions if p.recipe is not None)

    def unlearned_exact(self, base: BaseKey, elements: ElementVector) -> list[Potion]:
        """Неизученные рецепты, которые ровно совпадают с этой варкой (FR-14.7)."""
        known = self._known()
        if known is None:
            return []
        ids = self._index.get((base, elements), set()) - known
        return sorted(
            (self.raw_potion(i) for i in ids if not self.raw_potion(i).hidden),
            key=lambda p: p.name.casefold(),
        )

    # ── особые основы (П-4.4) ─────────────────────────────────────────────
    def special_bases(self, *, include_hidden: bool = False) -> list[Ingredient]:
        """Реагенты категории «Основа»."""
        return [
            i
            for i in self.ingredients(include_hidden=include_hidden)
            if i.category is IngredientCategory.BASE
        ]

    def base_names(self) -> dict[str, str]:
        """id особой основы → название: для подписей рецептов и предупреждений."""
        return {
            i.id: i.name for i in self._catalog.ingredients if i.category is IngredientCategory.BASE
        }

    def bases_text(self, recipe: Recipe) -> str:
        """«Жидкая или вязкая», «Любая» или название особой основы."""
        return recipe.format_bases_ru(self.base_names())

    def recipes_requiring(self, ingredient_id: str) -> list[Potion]:
        """Зелья, чей рецепт требует эту особую основу — среди известных персонажу."""
        return [
            p
            for p in self.potions()
            if p.recipe is not None and p.recipe.required_base_id == ingredient_id
        ]

    def is_required_base(self, ingredient_id: str) -> bool:
        """Нужна ли основа хоть одному рецепту справочника (знает он о нём или нет)."""
        return any(
            p.recipe is not None and p.recipe.required_base_id == ingredient_id
            for p in self._catalog.potions
        )

    def families(self) -> list[str]:
        return sorted({p.family for p in self._catalog.potions if p.family})

    def habitats(self) -> list[str]:
        found: set[str] = set()
        for ingredient in self._catalog.ingredients:
            found.update(ingredient.habitats)
        return sorted(found)

    # ── проверки ──────────────────────────────────────────────────────────
    def validate_ingredient(self, ingredient: Ingredient) -> list[Message]:
        """Предупреждения П-3.2. Ошибка (занятое имя) бросается при сохранении."""
        return check_ingredient(ingredient)

    def validate_recipe(self, potion: Potion, recipe: Recipe | None) -> list[Message]:
        """Проверка конфликтов рецепта (П-5.6, FR-2.5)."""
        if recipe is None:
            return []
        names = {p.id: p.name for p in self._catalog.potions}
        return check_recipe(potion, recipe, self._index, names, self.base_names())

    def potion_warnings(self, potion: Potion) -> list[Message]:
        return self.validate_recipe(potion, potion.recipe)

    def all_warnings(self) -> dict[str, list[Message]]:
        """Предупреждения по всему справочнику: для пометок в списках (FR-2.5)."""
        result: dict[str, list[Message]] = {}
        for ingredient in self._catalog.ingredients:
            messages = check_ingredient(ingredient)
            if messages:
                result[ingredient.id] = messages
        for potion in self._catalog.potions:
            messages = self.potion_warnings(potion)
            if messages:
                result[potion.id] = messages
        return result

    def _check_name_free(self, name: str, own_id: str | None, items: Iterable) -> None:
        key = normalize_name(name)
        if not key:
            raise AlchimistError(ErrorCode.EMPTY_NAME)
        for item in items:
            if item.id != own_id and normalize_name(item.name) == key:
                raise AlchimistError(ErrorCode.DUPLICATE_NAME, name=name, id=item.id)

    def new_ingredient_id(self, name: str) -> str:
        """Значения типов основ заняты: id особой основы с ними не должен совпадать (П-4.4)."""
        taken = {i.id for i in self._catalog.ingredients} | {str(b.value) for b in BASE_ORDER}
        return unique_id(name, taken)

    def new_potion_id(self, name: str) -> str:
        return unique_id(name, {p.id for p in self._catalog.potions})

    # ── запись: реагенты (FR-1.3) ─────────────────────────────────────────
    def add_ingredient(self, ingredient: Ingredient) -> tuple[Ingredient, list[Message]]:
        self._check_name_free(ingredient.name, None, self._catalog.ingredients)
        item = ingredient.copy(
            id=ingredient.id or self.new_ingredient_id(ingredient.name), updated_at=_now()
        )
        if self._catalog.ingredient_by_id(item.id):
            item = item.copy(id=self.new_ingredient_id(item.name))
        self._catalog.ingredients.append(item)
        self.repo.save_ingredients(self._catalog.ingredients)
        self.bus.publish(CatalogChanged(ingredient_ids=(item.id,)))
        return item, check_ingredient(item)

    def update_ingredient(self, ingredient: Ingredient) -> tuple[Ingredient, list[Message]]:
        self._check_name_free(ingredient.name, ingredient.id, self._catalog.ingredients)
        items = self._catalog.ingredients
        for i, existing in enumerate(items):
            if existing.id == ingredient.id:
                items[i] = ingredient.copy(updated_at=_now())
                self.repo.save_ingredients(items)
                self.bus.publish(CatalogChanged(ingredient_ids=(ingredient.id,)))
                return items[i], check_ingredient(items[i])
        raise AlchimistError(ErrorCode.NOT_FOUND, id=ingredient.id)

    def delete_ingredient(self, ingredient_id: str, *, used: bool = False) -> None:
        """FR-1.5: то, что есть в инвентаре или журнале, не удаляется — только скрывается."""
        item = self.ingredient(ingredient_id)
        if used:
            raise AlchimistError(ErrorCode.INGREDIENT_IN_USE, name=item.name, id=item.id)
        self._catalog.ingredients = [i for i in self._catalog.ingredients if i.id != ingredient_id]
        self.repo.save_ingredients(self._catalog.ingredients)
        self.bus.publish(CatalogChanged(ingredient_ids=(ingredient_id,)))

    def set_ingredient_hidden(self, ingredient_id: str, hidden: bool) -> Ingredient:
        item, _ = self.update_ingredient(self.ingredient(ingredient_id).copy(hidden=hidden))
        return item

    # ── запись: зелья (FR-2.3, FR-2.4) ────────────────────────────────────
    def add_potion(self, potion: Potion) -> tuple[Potion, list[Message]]:
        self._check_name_free(potion.name, None, self._catalog.potions)
        item = potion.copy(id=potion.id or self.new_potion_id(potion.name), updated_at=_now())
        if self._catalog.potion_by_id(item.id):
            item = item.copy(id=self.new_potion_id(item.name))
        self._catalog.potions.append(item)
        self._reindex()
        self.repo.save_potions(self._catalog.potions)
        self.bus.publish(CatalogChanged(potion_ids=(item.id,)))
        return item, self.potion_warnings(item)

    def update_potion(self, potion: Potion) -> tuple[Potion, list[Message]]:
        self._check_name_free(potion.name, potion.id, self._catalog.potions)
        items = self._catalog.potions
        for i, existing in enumerate(items):
            if existing.id == potion.id:
                items[i] = potion.copy(updated_at=_now())
                self._reindex()
                self.repo.save_potions(items)
                self.bus.publish(CatalogChanged(potion_ids=(potion.id,)))
                return items[i], self.potion_warnings(items[i])
        raise AlchimistError(ErrorCode.NOT_FOUND, id=potion.id)

    def set_recipe(self, potion_id: str, recipe: Recipe | None) -> tuple[Potion, list[Message]]:
        """Ввод или изменение рецепта (FR-2.4). Проверка П-5.6 — в результате."""
        potion = self.raw_potion(potion_id)
        return self.update_potion(potion.copy(recipe=recipe))

    def delete_potion(self, potion_id: str, *, used: bool = False) -> None:
        item = self.raw_potion(potion_id)
        if used:
            raise AlchimistError(ErrorCode.POTION_IN_USE, name=item.name, id=item.id)
        self._catalog.potions = [p for p in self._catalog.potions if p.id != potion_id]
        self._reindex()
        self.repo.save_potions(self._catalog.potions)
        self.bus.publish(CatalogChanged(potion_ids=(potion_id,)))

    def set_potion_hidden(self, potion_id: str, hidden: bool) -> Potion:
        item, _ = self.update_potion(self.raw_potion(potion_id).copy(hidden=hidden))
        return item

    # ── массовая замена (импорт) ──────────────────────────────────────────
    def replace_all(self, catalog: Catalog) -> None:
        self._catalog = catalog
        self._reindex()
        self.repo.save(catalog)
        self.bus.publish(CatalogChanged())
