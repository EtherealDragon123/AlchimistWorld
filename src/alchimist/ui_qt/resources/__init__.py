"""Картинки интерфейса: значок приложения."""

from pathlib import Path

RESOURCES = Path(__file__).parent


def app_icon_path() -> Path:
    """Значок окна и панели задач."""
    return RESOURCES / "icon.png"
