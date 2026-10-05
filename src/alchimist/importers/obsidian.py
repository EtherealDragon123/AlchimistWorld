"""Импорт реагентов и зелий из Obsidian-заметок (FR-10.1, 03 §7)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from alchimist.core.elements import ELEMENT_NAMES_RU, ElementVector, parse_element
from alchimist.core.errors import Message, Severity, WarningCode, warning
from alchimist.core.ids import normalize_name, unique_id
from alchimist.core.models import (
    ALL_BASES,
    BASE_NAMES_RU,
    TAG_BLACK_MARKET,
    BaseType,
    Catalog,
    Ingredient,
    IngredientCategory,
    Potion,
    PotionKind,
    Rarity,
    Recipe,
)

# ── Разбор общих кусочков ─────────────────────────────────────────────────────
#: Редкость определяется по основе слова. Порядок важен: «необычн» проверяется
#: раньше «обычн», иначе «Необычная трава» станет обычной (03 §7.2).
_RARITY_RULES: tuple[tuple[str, Rarity], ...] = (
    ("необычн", Rarity.UNCOMMON),
    ("обычн", Rarity.COMMON),
    ("очень редк", Rarity.EPIC),
    ("эпическ", Rarity.EPIC),
    ("редк", Rarity.RARE),
    ("легендарн", Rarity.LEGENDARY),
)

_CATEGORY_RULES: tuple[tuple[str, IngredientCategory], ...] = (
    ("трава", IngredientCategory.HERB),
    ("растение", IngredientCategory.PLANT),
    ("эссенци", IngredientCategory.ESSENCE),
)

_KIND_RULES: tuple[tuple[str, PotionKind], ...] = (
    ("яд", PotionKind.POISON),
    ("масло", PotionKind.OIL),
    ("мазь", PotionKind.OIL),
    ("зелье", PotionKind.POTION),
)

_BASE_RULES: tuple[tuple[str, frozenset[BaseType]], ...] = (
    ("люб", ALL_BASES),
    ("жидк", frozenset({BaseType.LIQUID})),
    ("вязк", frozenset({BaseType.VISCOUS})),
    ("взрывн", frozenset({BaseType.EXPLOSIVE})),
)

_EMPHASIS = re.compile(r"[*_]+")
_PARENS = re.compile(r"\(([^)]*)\)")
_HEADING = re.compile(r"^(#{1,6})\s*(.*)$")


def _clean(text: str) -> str:
    """Снимает `**`, `_`, пробелы по краям."""
    return _EMPHASIS.sub("", text).strip()


def _fold(text: str) -> str:
    return _clean(text).casefold().replace("ё", "е")


def _without_parens(text: str) -> str:
    """Скобки из строки типа убираются: там места обитания и пометки, а не редкость.

    Иначе «Редкое зелье *(в файле указано как Необычное…)*» станет необычным.
    """
    return _PARENS.sub(" ", text)


def parse_rarity(line: str) -> Rarity | None:
    """Редкость по основе слова (03 §7.2)."""
    folded = _fold(_without_parens(line))
    for stem, rarity in _RARITY_RULES:
        if stem.replace("ё", "е") in folded:
            return rarity
    return None


def parse_category(line: str, default: IngredientCategory) -> IngredientCategory:
    folded = _fold(_without_parens(line))
    for stem, category in _CATEGORY_RULES:
        if stem in folded:
            return category
    return default


def parse_kind(line: str) -> PotionKind:
    folded = _fold(_without_parens(line))
    for stem, kind in _KIND_RULES:
        if stem in folded:
            return kind
    return PotionKind.POTION


def parse_bases(text: str, on_synonym: list[tuple[str, str]] | None = None) -> frozenset[BaseType]:
    """«Жидкая или вязкая» → обе; «Жидкость» → liquid; «Любая» → все три."""
    folded = _fold(text)
    found: set[BaseType] = set()
    for stem, bases in _BASE_RULES:
        if stem in folded:
            found |= bases
    if on_synonym is not None and "жидкост" in folded:
        on_synonym.append((_clean(text), BASE_NAMES_RU[BaseType.LIQUID]))
    return frozenset(found)


def parse_habitats(line: str) -> list[str]:
    """Скобки в строке типа: `(Лес)`, `, (Болота)`, `(_Луг_)`."""
    habitats: list[str] = []
    for group in _PARENS.findall(line):
        for part in group.split(","):
            name = _clean(part)
            if name:
                habitats.append(name)
    return habitats


def parse_elements(
    text: str,
    on_unknown: list[str] | None = None,
    on_synonym: list[tuple[str, str]] | None = None,
) -> ElementVector:
    """«Тьма, Тьма, Огонь» → {dark: 2, fire: 1}. Синонимы учитываются (П-1.2)."""
    elements = []
    for part in text.split(","):
        cleaned = _clean(part)
        if not cleaned:
            continue
        element = parse_element(cleaned)
        if element is None:
            if on_unknown is not None:
                on_unknown.append(cleaned)
            continue
        if on_synonym is not None and _fold(cleaned) != _fold(ELEMENT_NAMES_RU[element]):
            on_synonym.append((cleaned, ELEMENT_NAMES_RU[element]))
        elements.append(element)
    return ElementVector.from_elements(elements)


# ── Блоки файла ───────────────────────────────────────────────────────────────
@dataclass(slots=True)
class Block:
    """Заголовок и его строки до следующего заголовка того же или высшего уровня."""

    level: int
    title: str
    lines: list[str] = field(default_factory=list)
    source: str = ""
    line_no: int = 0


def split_blocks(text: str, level: int, source: str = "") -> Iterator[Block]:
    """Режет файл на записи по заголовкам нужного уровня.

    Запись тянется до следующего `#` того же или более высокого уровня;
    разделители `---` пропускаются (03 §7.2, §7.3).
    """
    current: Block | None = None
    for number, raw in enumerate(text.splitlines(), start=1):
        match = _HEADING.match(raw)
        if match:
            depth = len(match.group(1))
            if depth <= level:
                if current is not None:
                    yield current
                    current = None
                if depth == level:
                    current = Block(depth, _clean(match.group(2)), [], source, number)
                continue
        if current is not None:
            if raw.strip() == "---":
                continue
            current.lines.append(raw)
    if current is not None:
        yield current


def _first_meaningful(lines: Iterable[str]) -> tuple[int, str]:
    for i, line in enumerate(lines):
        if line.strip():
            return i, line
    return -1, ""


# ── Отчёт ─────────────────────────────────────────────────────────────────────
@dataclass(slots=True)
class ImportReport:
    """Что нашли и на что стоит посмотреть (FR-10.1)."""

    ingredients: list[Ingredient] = field(default_factory=list)
    potions: list[Potion] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    files: list[str] = field(default_factory=list)

    @property
    def known_recipes(self) -> int:
        return sum(1 for p in self.potions if p.recipe is not None)

    def warn(self, code: WarningCode, **params: object) -> None:
        self.messages.append(warning(code, **params))

    def note(self, code: WarningCode, **params: object) -> None:
        """Справочная запись в отчёт: не проблема, просто «вот что мы сделали»."""
        message = Message(code, dict(params), Severity.INFO)
        if message not in self.messages:
            self.messages.append(message)

    def catalog(self) -> Catalog:
        return Catalog(list(self.ingredients), list(self.potions))


# ── Реагенты (03 §7.2) ────────────────────────────────────────────────────────
#: Файл → категория по умолчанию.
INGREDIENT_FILES: tuple[tuple[str, IngredientCategory], ...] = (
    ("Растения.md", IngredientCategory.PLANT),
    ("Эссенции.md", IngredientCategory.ESSENCE),
    ("С существ.md", IngredientCategory.CREATURE),
)

_REAGENT_LINE = re.compile(r"реагент\w*\s*[:：]", re.IGNORECASE)


def parse_ingredient_block(
    block: Block,
    default_category: IngredientCategory,
    report: ImportReport,
    taken: set[str],
) -> Ingredient | None:
    name = block.title
    if not name:
        return None

    type_index, type_line = _first_meaningful(block.lines)
    rarity = parse_rarity(type_line)
    if rarity is None:
        report.warn(
            WarningCode.IMPORT_UNKNOWN_RARITY, name=name, source=block.source, line=block.line_no
        )
        rarity = Rarity.COMMON

    category = (
        default_category
        if default_category is IngredientCategory.CREATURE
        else parse_category(type_line, default_category)
    )
    habitats = parse_habitats(type_line)

    elements = ElementVector()
    elements_index = -1
    unknown: list[str] = []
    synonyms: list[tuple[str, str]] = []
    for i, line in enumerate(block.lines):
        if i <= type_index:
            continue
        if _REAGENT_LINE.search(_clean(line)):
            elements_index = i
            elements = parse_elements(_clean(line).split(":", 1)[1], unknown, synonyms)
            break
    if elements_index < 0:
        report.warn(
            WarningCode.IMPORT_NO_ELEMENTS, name=name, source=block.source, line=block.line_no
        )
    for value in unknown:
        report.warn(WarningCode.IMPORT_UNKNOWN_ELEMENT, name=name, value=value)
    for written, canonical in synonyms:
        report.note(WarningCode.IMPORT_SYNONYM_APPLIED, value=written, canonical=canonical)

    description_lines = block.lines[type_index + 1 : elements_index if elements_index > 0 else None]
    description = "\n".join(description_lines).strip()
    if _fold(description) == "описание":  # заглушка `_Описание_` из Эссенций
        description = ""

    ingredient_id = unique_id(name, taken)
    if ingredient_id != unique_id(name, set()):
        report.warn(WarningCode.IMPORT_DUPLICATE_NAME, name=name, id=ingredient_id)
    taken.add(ingredient_id)

    return Ingredient(
        id=ingredient_id,
        name=name,
        rarity=rarity,
        category=category,
        is_herb=category in (IngredientCategory.HERB, IngredientCategory.PLANT),
        elements=elements,
        habitats=habitats,
        description=description,
    )


def import_ingredients(root: Path, report: ImportReport) -> None:
    taken: set[str] = set()
    by_name: dict[str, str] = {}
    base = root / "Ингридиенты" / "По видам"
    for filename, category in INGREDIENT_FILES:
        path = base / filename
        if not path.exists():
            continue
        report.files.append(str(path.relative_to(root)))
        text = path.read_text(encoding="utf-8")
        for block in split_blocks(text, level=3, source=filename):
            ingredient = parse_ingredient_block(block, category, report, taken)
            if ingredient is None:
                continue
            by_name[normalize_name(ingredient.name)] = ingredient.id
            report.ingredients.append(ingredient)
    check_indexes(root, by_name, report)


#: Указатели `По реагентам/*.md` не импортируются, только сверяются (03 §7.1).
_WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def check_indexes(root: Path, by_name: dict[str, str], report: ImportReport) -> None:
    """Сверка указателей: подпись ссылки должна совпадать с названием карточки."""
    base = root / "Ингридиенты" / "По реагентам"
    if not base.exists():
        return
    for path in sorted(base.glob("*.md")):
        for target, label in _WIKILINK.findall(path.read_text(encoding="utf-8")):
            anchor = _clean(target.split("#", 1)[-1])
            shown = _clean(label) if label else anchor
            if not shown or not anchor:
                continue
            if normalize_name(shown) == normalize_name(anchor):
                continue
            report.warn(
                WarningCode.IMPORT_INDEX_MISMATCH,
                source=path.name,
                label=shown,
                target=anchor,
            )


# ── Зелья (03 §7.3) ───────────────────────────────────────────────────────────
#: Номер файла задаёт запасную редкость.
POTION_FILE_RARITY: dict[str, Rarity] = {
    "1": Rarity.COMMON,
    "2": Rarity.UNCOMMON,
    "3": Rarity.RARE,
    "4": Rarity.EPIC,
    "5": Rarity.LEGENDARY,
}

_RECIPE_HEAD = re.compile(r"^рецепт\w*\s*[:：]?", re.IGNORECASE)
_NOTE_LINE = re.compile(r"примечание", re.IGNORECASE)
_FAMILY_NOTE = re.compile(r"существует\s+в\s+верси|относ\w*\s+к\s+редкости", re.IGNORECASE)
_NAME_VARIANT = re.compile(r"^(.*?)\s*\(([^()]*)\)\s*$")


def _recipe_start(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if _RECIPE_HEAD.match(_clean(line)):
            return i
    return -1


def parse_recipe_block(
    lines: list[str], report: ImportReport, name: str
) -> tuple[Recipe | None, str | None]:
    """Разбор блока рецепта. Не разобралось → (None, сырой текст) (03 §7.3)."""
    raw = "\n".join(_clean(line) for line in lines if _clean(line))
    body = _RECIPE_HEAD.sub("", raw, count=1).strip()
    if not body:
        return None, None

    folded = body.casefold()
    if folded.startswith("неизвестен") or folded.startswith("неизвестно"):
        return None, None

    bases: frozenset[BaseType] = frozenset()
    elements: ElementVector | None = None
    unknown: list[str] = []
    synonyms: list[tuple[str, str]] = []
    unparsed = False
    for line in body.splitlines():
        cleaned = _clean(line)
        low = cleaned.casefold()
        if low.startswith("основа"):
            bases = parse_bases(cleaned.split(":", 1)[-1], synonyms)
        elif _REAGENT_LINE.search(cleaned):
            tail = cleaned.split(":", 1)[-1]
            if re.search(r"\d|случайн|рандомн", tail, re.IGNORECASE):
                unparsed = True  # Бармаглот: «3 или больше рандомных реагентов»
                continue
            elements = parse_elements(tail, unknown, synonyms)
        elif cleaned:
            unparsed = True  # блок «Рецепты:» с вариантами и прочее

    for value in unknown:
        report.warn(WarningCode.IMPORT_UNKNOWN_ELEMENT, name=name, value=value)
    for written, canonical in synonyms:
        report.note(WarningCode.IMPORT_SYNONYM_APPLIED, value=written, canonical=canonical)

    if unparsed or not bases or elements is None or elements.is_empty:
        report.warn(WarningCode.IMPORT_RECIPE_UNPARSED, name=name, text=body)
        return None, body
    return Recipe(bases=bases, elements=elements), None


def parse_potion_block(
    block: Block,
    fallback_rarity: Rarity,
    report: ImportReport,
    taken: set[str],
) -> Potion | None:
    name = block.title
    if not name:
        return None

    type_index, type_line = _first_meaningful(block.lines)
    rarity = parse_rarity(type_line) or fallback_rarity
    kind = parse_kind(type_line)

    tags: set[str] = set()
    for group in _PARENS.findall(type_line):
        text = _clean(group)
        if not text:
            continue
        if "рынок" in text.casefold():
            tags.add(TAG_BLACK_MARKET)
        else:
            report.warn(WarningCode.IMPORT_UNKNOWN_TAG, name=name, value=text)

    recipe_index = _recipe_start(block.lines[type_index + 1 :])
    recipe_index = recipe_index + type_index + 1 if recipe_index >= 0 else len(block.lines)

    description_lines: list[str] = []
    family: str | None = None
    for line in block.lines[type_index + 1 : recipe_index]:
        if _NOTE_LINE.search(line):
            if _FAMILY_NOTE.search(line):
                match = _NAME_VARIANT.match(name)
                if match:
                    family = match.group(1).strip()
            continue  # строка «Примечание» в описание не идёт
        description_lines.append(line)

    recipe, recipe_note = parse_recipe_block(block.lines[recipe_index:], report, name)

    potion_id = unique_id(name, taken)
    if potion_id != unique_id(name, set()):
        report.warn(WarningCode.IMPORT_DUPLICATE_NAME, name=name, id=potion_id)
    taken.add(potion_id)

    return Potion(
        id=potion_id,
        name=name,
        rarity=rarity,
        kind=kind,
        family=family,
        tags=tags,
        description_md="\n".join(description_lines).strip(),
        recipe=recipe,
        recipe_note=recipe_note,
    )


def import_potions(root: Path, report: ImportReport) -> None:
    taken: set[str] = set()
    base = root / "Зелья"
    if not base.exists():
        return
    for path in sorted(base.glob("*.md")):
        fallback = POTION_FILE_RARITY.get(path.name[0], Rarity.COMMON)
        report.files.append(str(path.relative_to(root)))
        text = path.read_text(encoding="utf-8")
        for block in split_blocks(text, level=2, source=path.name):
            potion = parse_potion_block(block, fallback, report, taken)
            if potion is not None:
                report.potions.append(potion)


def import_obsidian(root: Path) -> ImportReport:
    """Разбирает папку `Алхимия/` целиком (03 §7)."""
    report = ImportReport()
    root = Path(root)
    import_ingredients(root, report)
    import_potions(root, report)
    return report
