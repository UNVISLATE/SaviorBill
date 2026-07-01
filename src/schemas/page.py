"""Обобщённая схема постраничного ответа."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Страница списка: ``items`` + метаданные пагинации.

    :arg items: элементы текущей страницы.
    :arg total: общее число записей по фильтру (без учёта limit/offset).
    :arg limit: запрошенный размер страницы.
    :arg offset: смещение от начала выборки.
    """

    items: list[T] = Field(description="Элементы текущей страницы")
    total: int = Field(description="Всего записей по фильтру (обязательно)")
    limit: int = Field(description="Размер страницы (обязательно)")
    offset: int = Field(description="Смещение выборки (обязательно)")


__all__ = ["Page"]
