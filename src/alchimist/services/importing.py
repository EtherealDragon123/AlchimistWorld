"""Импорт из Obsidian как сценарий приложения (FR-10.1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from alchimist.core.errors import Message, Severity
from alchimist.core.models import BASE_NAMES_RU, RARITY_NAMES_RU, Catalog, Rarity
from alchimist.core.rules import check_catalog
from alchimist.importers.obsidian import ImportReport, import_obsidian
from alchimist.services.catalog import CatalogService


@dataclass(frozen=True, slots=True)
class ImportResult:
    report: ImportReport
    rule_messages: tuple[Message, ...]
    applied: bool

    @property
    def catalog(self) -> Catalog:
        return self.report.catalog()

    @property
    def messages(self) -> list[Message]:
        return [*self.report.messages, *self.rule_messages]


def run_import(source: Path, catalog: CatalogService | None, *, dry_run: bool) -> ImportResult:
    """Разбирает заметки и, если не `--dry-run`, записывает справочник."""
    report = import_obsidian(Path(source))
    rules = check_catalog(report.ingredients, report.potions)
    applied = False
    if not dry_run and catalog is not None:
        catalog.replace_all(report.catalog())
        applied = True
    return ImportResult(report, tuple(rules), applied)


def render_report(result: ImportResult, source: Path) -> str:
    """`import-report.md` рядом с каталогом (03 §7)."""
    report = result.report
    lines: list[str] = [
        "# Отчёт об импорте из Obsidian",
        "",
        f"- Источник: `{source}`",
        f"- Дата: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- Реагентов: **{len(report.ingredients)}**",
        f"- Зелий: **{len(report.potions)}**, из них с известным рецептом: "
        f"**{report.known_recipes}**",
        f"- Записано в справочник: {'да' if result.applied else 'нет (пробный запуск)'}",
        "",
        "## Разобранные файлы",
        "",
    ]
    lines += [f"- `{name}`" for name in report.files]

    by_rarity: dict[int, int] = {}
    for ingredient in report.ingredients:
        by_rarity[int(ingredient.rarity)] = by_rarity.get(int(ingredient.rarity), 0) + 1
    lines += ["", "## Реагенты по редкости", "", "| Редкость | Сколько |", "|---|---|"]
    lines += [f"| {RARITY_NAMES_RU[Rarity(r)]} ({r}) | {n} |" for r, n in sorted(by_rarity.items())]

    known = [p for p in report.potions if p.recipe is not None]
    lines += ["", "## Известные рецепты", "", "| Зелье | Основа | Элементы |", "|---|---|---|"]
    for potion in sorted(known, key=lambda p: (p.rarity, p.name)):
        bases = ", ".join(BASE_NAMES_RU[b] for b in potion.recipe.sorted_bases())
        lines.append(f"| {potion.name} | {bases} | {potion.recipe.elements.format_ru()} |")

    from alchimist.i18n import describe

    for title, severity in (
        ("Предупреждения", Severity.WARNING),
        ("Проверки правил", Severity.ERROR),
        ("Замечания", Severity.INFO),
    ):
        selected = [m for m in result.messages if m.severity is severity]
        if not selected:
            continue
        lines += ["", f"## {title}", ""]
        lines += [f"- {describe(m)}" for m in selected]

    if not any(m.severity is not Severity.INFO for m in result.messages):
        lines += ["", "Проблем не найдено."]

    return "\n".join(lines) + "\n"
