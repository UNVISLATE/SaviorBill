"""Контракты управления лимитами частоты запросов (админ)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RateLimitRule(BaseModel):
    """Действующее правило лимита для категории.

    :arg kind: категория лимита (default/auth/mail/sensitive).
    :arg max_hits: максимум обращений в окне.
    :arg window: размер окна в секундах.
    :arg overridden: задано ли значение вручную (иначе — ENV-дефолт).
    """

    kind: str = Field(description="Категория лимита (обязательно)")
    max_hits: int = Field(description="Максимум обращений в окне (обязательно)")
    window: int = Field(description="Размер окна в секундах (обязательно)")
    overridden: bool = Field(
        description="True — значение переопределено админом; False — ENV-дефолт"
    )


class RateLimitPatch(BaseModel):
    """Переопределение правила лимита категории.

    - `max_hits`: максимум обращений в окне (обязательно)
    - `window`: размер окна в секундах (обязательно)
    """

    max_hits: int = Field(gt=0, description="Максимум обращений в окне (обязательно)")
    window: int = Field(gt=0, description="Размер окна в секундах (обязательно)")


__all__ = ["RateLimitRule", "RateLimitPatch"]
