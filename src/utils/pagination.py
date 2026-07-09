"""Помощник постраничной выборки поверх SQLAlchemy select.

Модель пагинации (см. UPDATE_PLAN.md): три параметра запроса —
``limit`` (сколько отдать), ``offset`` (приоритетное смещение) и ``pass``/``skip``
(сколько пропустить, если ``offset`` не задан). Если ``offset`` задан — ``pass``
игнорируется. Ответ (:class:`schemas.page.Page`) помимо элементов несёт ``total``
(всего записей) и ``has_more`` (есть ли ещё страницы) — для динамической подгрузки.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypeVar

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

M = TypeVar("M")
S = TypeVar("S")


@dataclass(slots=True)
class PageParams:
    """Разрешённые параметры пагинации (эффективное смещение уже вычислено)."""

    limit: int
    offset: int


def page_params(
    limit: int = Query(
        50,
        ge=1,
        le=200,
        description="Page size — how many records to return",
    ),
    offset: int | None = Query(
        None,
        ge=0,
        description="Explicit offset; if set, `pass` is ignored",
    ),
    skip: int = Query(
        0,
        ge=0,
        alias="pass",
        description="Records to skip when `offset` is not set (for infinite scroll)",
    ),
) -> PageParams:
    """FastAPI-зависимость: свести ``limit``/``offset``/``pass`` к :class:`PageParams`.

    :arg limit: размер страницы.
    :arg offset: приоритетное смещение (если задано — ``pass`` игнорируется).
    :arg skip: смещение-«пропуск» (алиас запроса ``pass``), применяется без ``offset``.
    :return: разрешённые параметры пагинации.
    """
    effective = offset if offset is not None else skip
    return PageParams(limit=limit, offset=effective)


async def paginate(
    session: AsyncSession,
    stmt: Select,
    mapper: Callable[[M], S],
    *,
    limit: int,
    offset: int,
) -> tuple[list[S], int, bool]:
    """Посчитать total и вернуть страницу результатов ``stmt``.

    :arg session: активная сессия БД.
    :arg stmt: базовый select (без limit/offset), с нужными where/order_by.
    :arg mapper: преобразование ORM-строки в схему ответа.
    :arg limit: размер страницы.
    :arg offset: эффективное смещение выборки.
    :return: кортеж (элементы страницы, общее число записей, есть ли ещё страницы).
    """
    total = await session.scalar(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    )
    total = int(total or 0)
    rows = await session.scalars(stmt.limit(limit).offset(offset))
    items = [mapper(r) for r in rows]
    has_more = (offset + len(items)) < total
    return items, total, has_more


async def paginate_rows(
    session: AsyncSession,
    stmt: Select,
    mapper: Callable[[object], S],
    *,
    limit: int,
    offset: int,
) -> tuple[list[S], int, bool]:
    """Как :func:`paginate`, но для select с несколькими колонками/агрегатами.

    ``session.scalars()`` (использует :func:`paginate`) отдаёт только первую
    колонку select — не годится для группировок (``select(col1, func.count())``
    и т.п.). Здесь вместо этого ``session.execute()`` — ``mapper`` получает
    ``Row`` целиком (обычно через ``row._mapping`` или именованные атрибуты).

    :arg session: активная сессия БД.
    :arg stmt: базовый select (без limit/offset), с нужными where/group_by/order_by.
    :arg mapper: преобразование ``Row`` в схему ответа.
    :arg limit: размер страницы.
    :arg offset: эффективное смещение выборки.
    :return: кортеж (элементы страницы, общее число записей, есть ли ещё страницы).
    """
    total = await session.scalar(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    )
    total = int(total or 0)
    rows = (await session.execute(stmt.limit(limit).offset(offset))).all()
    items = [mapper(r) for r in rows]
    has_more = (offset + len(items)) < total
    return items, total, has_more


__all__ = ["PageParams", "page_params", "paginate", "paginate_rows"]
