"""Контракты управления лимитами частоты запросов (админ)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RateLimitRule(BaseModel):
    """Active rate limit rule."""

    kind: str = Field(description="Limit category")
    max_hits: int = Field(description="Max requests in window")
    window: int = Field(description="Window size in seconds")
    overridden: bool = Field(
        description="True = admin override; False = ENV default"
    )


class RateLimitPatch(BaseModel):
    """Override rate limit rule."""

    max_hits: int = Field(gt=0, description="Max requests in window")
    window: int = Field(gt=0, description="Window size in seconds")


__all__ = ["RateLimitRule", "RateLimitPatch"]
