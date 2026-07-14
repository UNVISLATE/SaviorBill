"""Обобщённая схема постраничного ответа."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Paginated list response."""

    items: list[T] = Field(description="Page items")
    total: int = Field(description="Total items")
    limit: int = Field(description="Page size")
    offset: int = Field(description="Effective offset")
    has_more: bool = Field(description="More items available")


__all__ = ["Page"]
