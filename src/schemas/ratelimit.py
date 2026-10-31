"""Контракты управления лимитами частоты запросов (админ)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RateLimitRule(BaseModel):
    """Active rate limit rule."""

    kind: str = Field(description="Limit category")
    max_hits: int = Field(description="Max requests in window")
    window: int = Field(description="Window size in seconds")
    burst_hits: int = Field(default=15, description="Burst limit in short window")
    burst_window: int = Field(default=1, description="Burst window in seconds (usually 1s)")
    overridden: bool = Field(description="True = admin override; False = ENV default")


class RateLimitPatch(BaseModel):
    """Override rate limit rule."""

    max_hits: int = Field(gt=0, description="Max requests in window")
    window: int = Field(gt=0, description="Window size in seconds")
    burst_hits: int | None = Field(default=None, gt=0, description="Burst limit in short window")


__all__ = ["RateLimitRule", "RateLimitPatch"]
