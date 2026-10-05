"""Разметка описаний (FR-2.6)."""

from __future__ import annotations

from alchimist.ui_qt.markdown import to_html, to_plain


def test_bold_and_italic() -> None:
    assert to_html("**жирный**") == "<p><b>жирный</b></p>"
    assert to_html("_курсив_") == "<p><i>курсив</i></p>"
    assert to_html("*курсив*") == "<p><i>курсив</i></p>"


def test_lists() -> None:
    assert to_html("- один\n- два") == "<ul><li>один</li><li>два</li></ul>"
    assert to_html("1. один\n2. два") == "<ol><li>один</li><li>два</li></ol>"


def test_paragraphs_and_headings() -> None:
    html = to_html("# Заголовок\n\nПервый абзац.\n\nВторой абзац.")
    assert html == "<h3>Заголовок</h3><p>Первый абзац.</p><p>Второй абзац.</p>"


def test_html_is_escaped() -> None:
    assert to_html("<script>alert(1)</script>") == "<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>"


def test_empty() -> None:
    assert to_html("   ") == ""


def test_plain_summary() -> None:
    assert to_plain("**Вы** восстанавливаете 2к4+2 хитов") == "Вы восстанавливаете 2к4+2 хитов"
    assert to_plain("а" * 200).endswith("…")
