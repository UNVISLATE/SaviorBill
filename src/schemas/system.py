from __future__ import annotations

from pydantic import BaseModel, Field


class HealthCheck(BaseModel):
    """Контракт проверки здоровья сервиса."""

    status: str = Field(default="ok", description="Статус сервиса")
    app_name: str = Field(default="SaviorBill", description="Название приложения")
    app_version: str = Field(default="0.0.1dev", description="Версия приложения")


__all__ = ["HealthCheck"]
