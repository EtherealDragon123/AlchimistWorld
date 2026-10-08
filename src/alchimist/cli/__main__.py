"""`python -m alchimist …` — консольный интерфейс (этап 2)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from alchimist.core.elements import ELEMENT_NAMES_RU
from alchimist.core.errors import AlchimistError, Severity
from alchimist.core.models import (
    BASE_NAMES_RU,
    CATEGORY_NAMES_RU,
    KIND_NAMES_RU,
    KIT_NAMES_RU,
    RARITY_NAMES_RU,
    JournalEntryType,
    Kit,
    Outcome,
)
from alchimist.i18n import _, describe, set_language
from alchimist.services import build_app
from alchimist.services.app import AppService


def _app(args: argparse.Namespace) -> AppService:
    return build_app(Path(args.data).expanduser() if args.data else None, args.profile)


def _print_messages(messages, prefix: str = "") -> None:
    marks = {Severity.INFO: "·", Severity.WARNING: "!", Severity.ERROR: "×"}
    for message in messages:
        print(f"{prefix}{marks[message.severity]} {describe(message)}")


# ── справочник ────────────────────────────────────────────────────────────────
def cmd_catalog(args: argparse.Namespace) -> int:
    app = _app(args)
    if args.what == "ingredients":
        for item in app.catalog.ingredients():
            herb = " [травы]" if item.is_herb else ""
            habitats = f" ({', '.join(item.habitats)})" if item.habitats else ""
            print(
                f"{item.name:38} {RARITY_NAMES_RU[item.rarity]:12} "
                f"{CATEGORY_NAMES_RU[item.category]:10} {item.elements.format_ru():30}"
                f"{herb}{habitats}"
            )
    else:
        for item in app.catalog.potions():
            recipe = (
                f"{item.recipe.format_bases_ru()} · {item.recipe.elements.format_ru()}"
                if item.recipe
                else "рецепт неизвестен"
            )
            print(
                f"{item.name:44} {RARITY_NAMES_RU[item.rarity]:12} "
                f"{KIND_NAMES_RU[item.kind]:7} {recipe}"
            )
    return 0


# ── инвентарь ─────────────────────────────────────────────────────────────────
def _find_ingredient(app: AppService, needle: str):
    needle_folded = needle.casefold().replace("ё", "е")
    items = app.catalog.ingredients()
    exact = [
        i for i in items if i.id == needle or i.name.casefold().replace("ё", "е") == needle_folded
    ]
    if exact:
        return exact[0]
    partial = [i for i in items if needle_folded in i.name.casefold().replace("ё", "е")]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise SystemExit(f"Реагент не найден: {needle}")
    raise SystemExit("Подходит несколько: " + ", ".join(i.name for i in partial[:10]))


def cmd_inv(args: argparse.Namespace) -> int:
    app = _app(args)
    if args.action == "show":
        rows = app.inventory.reagent_rows(app.catalog.ingredient_map())
        for row in rows:
            print(f"{row.qty:>4} × {row.ingredient.name:38} {row.ingredient.elements.format_ru()}")
        total = app.inventory.element_summary(app.catalog.ingredient_map())
        print(f"\nВсего единиц: {total.format_ru()}" if total else "\nИнвентарь пуст.")
        potions = app.inventory.potion_rows(app.catalog.potion_map())
        if potions:
            print("\nЗелья:")
            for row in potions:
                print(f"{row.qty:>4} × {row.potion.name}")
        return 0

    ingredient = _find_ingredient(app, args.name)
    delta = args.qty if args.action == "add" else -args.qty
    qty = app.inventory.add_reagent(ingredient.id, delta)
    print(f"{ingredient.name}: {qty}")
    return 0


# ── подбор ────────────────────────────────────────────────────────────────────
def cmd_can_brew(args: argparse.Namespace) -> int:
    app = _app(args)
    kits = ", ".join(KIT_NAMES_RU[k] for k in app.settings.kits)
    print(f"Наборы: {kits}\n")
    rows = app.brewing.can_brew()
    if not rows:
        print("Пока ничего не сварить.")
        return 0
    for row in rows:
        print(
            f"{row.potion.name}  ({RARITY_NAMES_RU[row.potion.rarity].lower()})  ×{row.max_repeats}"
        )
        for option in row.options[: args.options]:
            picks = " + ".join(
                f"{p.ingredient.name}×{p.count}" if p.count > 1 else p.ingredient.name
                for p in option.combination.picks
            )
            # Основы у варианта может быть несколько: показывать одну — обманывать.
            extra = ""
            if not option.combination.is_exact:
                extra = f"   лишнее: {option.combination.excess.format_ru()}"
            print(
                f"    {option.format_bases_ru():18} · {picks}"
                f"   ×{option.portions} порц., Сл {option.difficulty.total}"
                f"   (повторов: {option.repeats}){extra}"
            )
    return 0


def cmd_almost(args: argparse.Namespace) -> int:
    app = _app(args)
    rows = app.brewing.almost(max_missing=args.max_missing)
    for row in rows:
        print(
            f"{row.potion.name}: не хватает {row.missing.format_ru()}"
            f"  (основа: {BASE_NAMES_RU[row.base].lower()})"
        )
        for filler in row.fillers:
            names = " + ".join(
                f"{p.ingredient.name}×{p.count}" if p.count > 1 else p.ingredient.name
                for p in filler.picks
            )
            print(f"    закрыть: {names}")
    if not rows:
        print("Нечего показать.")
    return 0


def _name_of(items: dict, item_id: str | None) -> str:
    item = items.get(item_id or "")
    return item.name if item else str(item_id)


# ── журнал и настройки ────────────────────────────────────────────────────────
def cmd_journal(args: argparse.Namespace) -> int:
    app = _app(args)
    potions = app.catalog.potion_map()
    ingredients = app.catalog.ingredient_map()
    for entry in app.journal.entries()[: args.limit]:
        stamp = entry.ts.strftime("%Y-%m-%d %H:%M")
        undone = "  [отменено]" if entry.undone else ""
        if entry.type is JournalEntryType.BREW:
            reagents = ", ".join(
                f"{_name_of(ingredients, r.ingredient_id)}×{r.qty}" for r in entry.reagents
            )
            got = ""
            if entry.result and entry.result.potion_id in potions:
                got = f" → {potions[entry.result.potion_id].name}"
            outcome = "успех" if entry.outcome is Outcome.SUCCESS else "провал"
            print(
                f"{stamp}  варка  {BASE_NAMES_RU[entry.base].lower() if entry.base else '—'}: "
                f"{reagents} = {entry.elements.format_ru()}  {outcome}{got}{undone}"
            )
        elif entry.type is JournalEntryType.DISTILL:
            reagents = ", ".join(
                f"{_name_of(ingredients, r.ingredient_id)}×{r.qty}" for r in entry.reagents
            )
            produced = ", ".join(
                f"{_name_of(ingredients, r.ingredient_id)}×{r.qty}" for r in entry.produced
            )
            print(
                f"{stamp}  разбор  {reagents} = {entry.elements.format_ru()}"
                f" → {produced or '—'}{undone}"
            )
        else:
            print(
                f"{stamp}  {entry.type.value:6} {_name_of(potions, entry.potion_id)} ×{entry.qty}"
            )
    return 0


def cmd_settings(args: argparse.Namespace) -> int:
    app = _app(args)
    if args.kits:
        kits = tuple(Kit(k) for k in args.kits)
        app.settings.set_kits(kits)
    if args.language:
        app.settings.set_language(args.language)
    if args.character:
        app.settings.set_character_name(args.character)
    settings = app.settings.settings
    print(f"Язык: {settings.language}")
    print(f"Наборы: {', '.join(KIT_NAMES_RU[k] for k in settings.kits)}")
    print(f"Персонаж: {settings.character_name or '—'}")
    print(f"Профиль: {settings.active_profile}")
    print(f"Данные: {app.paths.root}")
    print(f"Настройки: {app.paths.settings_file}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Прогоняет проверки П-3.2, П-5.2 и П-5.6 по всему справочнику."""
    app = _app(args)
    from alchimist.core.rules import check_catalog

    messages = check_catalog(app.catalog.catalog.ingredients, app.catalog.catalog.potions)
    _print_messages(messages)
    print(f"\nПроблем: {len(messages)}")
    return 1 if messages else 0


def cmd_export(args: argparse.Namespace) -> int:
    app = _app(args)
    path = app.exchange.export(Path(args.path), app.settings.settings.character_name)
    print(f"Справочник выгружен: {path}")
    return 0


def cmd_import_catalog(args: argparse.Namespace) -> int:
    app = _app(args)
    plan = app.exchange.plan(Path(args.path))
    print(f"От кого: {plan.exported_by or '—'} ({plan.exported_at or '—'})")
    print(
        f"Новых записей: {len(plan.added)}, расхождений: {len(plan.conflicts)}, "
        f"совпало: {plan.identical}"
    )
    for diff in plan.conflicts:
        print(f"  ≠ {diff.name}: {', '.join(diff.changed_fields())}")
    if args.dry_run:
        return 0
    from alchimist.services.exchange import MergeChoice

    default = MergeChoice.TAKE_THEIRS if args.prefer == "theirs" else MergeChoice.KEEP_MINE
    messages = app.exchange.apply(plan, default=default)
    _print_messages(messages, prefix="  ")
    print("Готово.")
    return 0


def cmd_elements(_args: argparse.Namespace) -> int:
    for element, name in ELEMENT_NAMES_RU.items():
        print(f"{element.value:6} {name}")
    return 0


# ── разбор аргументов ─────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alchimist", description=_("Помощник по алхимии для D&D"))
    parser.add_argument("--data", help="папка данных (иначе стандартная для ОС)")
    parser.add_argument("--profile", help="профиль персонажа")
    parser.add_argument("--lang", help="язык сообщений")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("catalog", help="показать справочник")
    p.add_argument("what", choices=["ingredients", "potions"])
    p.set_defaults(func=cmd_catalog)

    p = sub.add_parser("inv", help="инвентарь")
    p.add_argument("action", choices=["show", "add", "remove"])
    p.add_argument("name", nargs="?", default="", help="название реагента")
    p.add_argument("qty", nargs="?", type=int, default=1)
    p.set_defaults(func=cmd_inv)

    p = sub.add_parser("can-brew", help="что можно сварить (FR-5.1)")
    p.add_argument("--options", type=int, default=3, help="сколько вариантов показывать")
    p.set_defaults(func=cmd_can_brew)

    p = sub.add_parser("almost", help="чего не хватает (FR-6.1)")
    p.add_argument("--max-missing", type=int, default=2)
    p.set_defaults(func=cmd_almost)

    p = sub.add_parser("journal", help="журнал")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_journal)

    p = sub.add_parser("settings", help="настройки (FR-9.x)")
    p.add_argument("--kits", nargs="*", choices=[k.value for k in Kit])
    p.add_argument("--language")
    p.add_argument("--character")
    p.set_defaults(func=cmd_settings)

    p = sub.add_parser("check", help="проверить справочник по правилам")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("export", help="выгрузить справочник (FR-10.2)")
    p.add_argument("path")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("import-catalog", help="принять справочник от другого игрока (FR-10.3)")
    p.add_argument("path")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--prefer", choices=["mine", "theirs"], default="mine")
    p.set_defaults(func=cmd_import_catalog)

    p = sub.add_parser("elements", help="список элементов и их кодов")
    p.set_defaults(func=cmd_elements)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    set_language(args.lang)
    try:
        return args.func(args)
    except AlchimistError as exc:
        print(describe(exc.message), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
