"""DI шифрования секретов: единый источник SecBox для приложения."""

from __future__ import annotations

from fastapi import Request

from utils.config import AppConfig
from utils.sec.box import SecBox


def make_secbox(cfg: AppConfig) -> SecBox:
    """Собрать SecBox из резолвнутого ключа конфигурации."""
    return SecBox(cfg.SECRETS_KEY)


def get_secbox(request: Request) -> SecBox:
    """FastAPI-зависимость: SecBox на основе ключа из ``app.state.settings``."""
    cfg: AppConfig = request.app.state.settings
    return make_secbox(cfg)


__all__ = ["make_secbox", "get_secbox"]
