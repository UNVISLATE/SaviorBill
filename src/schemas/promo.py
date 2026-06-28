"""Контракты промокодов."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class PromoRedeem(BaseModel):
    """Активация промокода (bonus или service)."""

    code: str = Field(min_length=2, max_length=64)


class PromoResult(BaseModel):
    """Результат активации промокода."""

    kind: str
    message: str
    bonus_added: Decimal | None = None
    order_id: int | None = None


__all__ = ["PromoRedeem", "PromoResult"]
