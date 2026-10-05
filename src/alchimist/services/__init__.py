"""Сценарии приложения. Интерфейс вызывает только этот слой (NFR-1)."""

from alchimist.services.app import AppService, build_app

__all__ = ["AppService", "build_app"]
