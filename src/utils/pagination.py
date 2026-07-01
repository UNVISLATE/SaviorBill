"""Помощник постраничной выборки поверх SQLAlchemy select."""

from __future__ import annotations

from typing import Callable, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

M = TypeVar("M")
S = TypeVar("S")


async def paginate(
    session: AsyncSession,
    stmt: Select,
    mapper: Callable[[M], S],
    *,
    limit: int,
    offset: int,
) -> tuple[list[S], int]:
    """Посчитать total и вернуть страницу результатов ``stmt``.

    :arg session: активная сессия БД.
    :arg stmt: базовый select (без limit/offset), с нужными where/order_by.
    :arg mapper: преобразование ORM-строки в схему ответа.
    :arg limit: размер страницы.
    :arg offset: смещение выборки.
    :return: кортеж (элементы страницы, общее число записей).
    """
    total = await session.scalar(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    )
    rows = await session.scalars(stmt.limit(limit).offset(offset))
    return [mapper(r) for r in rows], int(total or 0)


__all__ = ["paginate"]
