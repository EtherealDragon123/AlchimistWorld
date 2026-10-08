"""Консольный интерфейс (этап 2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from alchimist.cli.__main__ import main


@pytest.fixture
def data_dir(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("ALCHIMIST_DATA_DIR", str(tmp_path))
    return tmp_path


def run(*args: str) -> int:
    return main(list(args))


def test_full_console_workflow(data_dir, capsys, campaign_file) -> None:
    run("import-catalog", str(campaign_file))
    capsys.readouterr()

    assert run("inv", "add", "Щёлкорех", "3") == 0
    assert "Щёлкорех: 3" in capsys.readouterr().out

    assert run("can-brew") == 0
    out = capsys.readouterr().out
    assert "Алхимический Огонь" in out
    assert "Щёлкорех×2" in out

    assert run("almost", "--max-missing", "1") == 0
    assert "не хватает" in capsys.readouterr().out

    assert run("check") == 0
    assert "Проблем: 0" in capsys.readouterr().out

    assert run("inv", "show") == 0
    assert "Огонь×3" in capsys.readouterr().out


def test_settings_roundtrip(data_dir, capsys) -> None:
    # Наборы и имя — у персонажа (FR-14.5): без него их некуда записать.
    assert run("settings", "--kits", "herbalist") == 1
    assert run("new-character", "Гримли", "--kits", "herbalist") == 0
    assert run("settings", "--kits", "herbalist", "poisoner", "--character", "Гримли Второй") == 0
    out = capsys.readouterr().out
    assert "Набор травника" in out
    assert "Гримли Второй" in out

    assert run("settings") == 0
    assert "Инструменты отравителя" in capsys.readouterr().out


def test_characters_and_learning(data_dir, capsys) -> None:
    """FR-14.x в консоли: два персонажа, GM по имени, изучение рецепта."""
    assert run("new-character", "Гримли") == 0
    assert run("learn", "Пламя Саламандры") == 0
    assert "Вязкая · Огонь×2, Свет×1" in capsys.readouterr().out

    assert run("export", str(data_dir / "x.json")) == 1  # игрок справочник не выгружает
    assert run("new-character", "gm") == 0
    assert run("export", str(data_dir / "x.json")) == 0

    assert run("switch", "Гримли") == 0
    capsys.readouterr()
    assert run("characters") == 0
    out = capsys.readouterr().out
    assert "* Гримли" in out
    assert "рецептов 21/25" in out  # 20 обычных + изученное
    assert "GM" in out


def test_export_and_import_catalog(data_dir, tmp_path, capsys, campaign_file) -> None:
    run("import-catalog", str(campaign_file))
    capsys.readouterr()

    target = tmp_path / "catalog.json"
    assert run("export", str(target)) == 0
    assert target.exists()

    assert run("import-catalog", str(target), "--dry-run") == 0
    out = capsys.readouterr().out
    assert "Новых записей: 0" in out
    assert "расхождений: 0" in out


def test_unknown_reagent_reports_error(data_dir) -> None:
    with pytest.raises(SystemExit):
        run("inv", "add", "Несуществующая трава", "1")


def test_elements_command(data_dir, capsys) -> None:
    assert run("elements") == 0
    out = capsys.readouterr().out
    assert "fire   Огонь" in out
    assert "air    Воздух" in out


def test_can_brew_shows_every_allowed_base(data_dir, capsys, campaign_file) -> None:
    """Вариант может годиться на нескольких основах — показывать одну нечестно.

    «Алхимический Огонь» варится на любой основе, а вывод показывал «Жидкая».
    """
    run("import-catalog", str(campaign_file))
    run("inv", "add", "Щёлкорех", "6")
    capsys.readouterr()

    assert run("can-brew") == 0
    out = capsys.readouterr().out
    assert "Алхимический Огонь" in out
    assert "Любая" in out
    # Порции и сложность появились вместе с П-8 — в консоли их тоже видно.
    assert "порц." in out and "Сл " in out


def test_journal_prints_distillation(data_dir, capsys, campaign_file) -> None:
    """Разбор на эссенции — не «зелье ×1», а своя строка (П-9)."""
    from alchimist.services import build_app

    run("import-catalog", str(campaign_file))
    capsys.readouterr()

    app = build_app(data_dir)
    app.inventory.set_reagent("sok-stalnogo-dereva", 1)  # Земля×2
    app.inventory.set_potion("distilliruyushchiy-ekstrakt", 1)
    app.distilling.distill({"sok-stalnogo-dereva": 1})

    assert run("journal") == 0
    out = capsys.readouterr().out
    assert "разбор" in out
    assert "Сок Стального Дерева×1" in out
    assert "Тусклая эссенция земли×1" in out
