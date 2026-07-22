"""Помощник постраничной выборки поверх SQLAlchemy select.

Модель пагинации: два параметра запроса — ``limit`` (сколько отдать) и
``offset`` (сколько пропустить). Ответ (:class:`schemas.page.Page`) помимо
элементов несёт ``total`` (всего записей) и ``has_more`` (есть ли ещё
страницы) — для динамической подгрузки.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence, TypeVar

from fastapi import HTTPException, Query, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

M = TypeVar("M")
S = TypeVar("S")


@dataclass(slots=True)
class PageParams:
    """Разрешённые параметры пагинации."""

    limit: int
    offset: int


def page_params(
    limit: int = Query(
        50,
        ge=1,
        le=200,
        description="Page size — how many records to return",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="How many records to skip",
    ),
) -> PageParams:
    """FastAPI-зависимость: свести query-параметры к :class:`PageParams`."""
    return PageParams(limit=limit, offset=offset)


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


def q_param(
    q: str | None = Query(
        None, description="Search text (exact substring match, falls back to "
        "fuzzy 'similar' matching if nothing is found)"
    ),
) -> str | None:
    """FastAPI-зависимость: query-параметр поиска (пустая строка = не искать)."""
    return q or None


def sort_param(
    sort: str | None = Query(
        None,
        description="Sort field; prefix with '-' for descending "
        "(e.g. 'created_at' or '-created_at')",
    ),
) -> str | None:
    """FastAPI-зависимость: query-параметр сортировки, разбор — в :func:`apply_sort`."""
    return sort or None


def apply_sort(stmt: Select, model: type, sort: str | None, allowed: Sequence[str]) -> Select:
    """Применить сортировку по allowlist-полю модели.

    ``field`` берётся ТОЛЬКО из ``allowed`` — никогда не собирается raw SQL
    из пользовательского ввода (риск SQL-инъекции через имя колонки при
    неаккуратном ``order_by(text(...))``). Незнакомое поле — 400, а не тихий
    игнор (иначе админ решит, что сортировка сработала, а список не изменился).

    :arg stmt: select без ``order_by`` (или с дефолтным — будет заменён).
    :arg model: ORM-модель, чьи колонки разрешено использовать для сортировки.
    :arg sort: ``"field"`` (по возрастанию) или ``"-field"`` (по убыванию).
    :arg allowed: allowlist имён полей для этого роута.
    """
    if not sort:
        return stmt
    descending = sort.startswith("-")
    field = sort[1:] if descending else sort
    if field not in allowed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"cannot sort by '{field}'; allowed: {', '.join(sorted(allowed))}",
        )
    col = getattr(model, field)
    return stmt.order_by(col.desc() if descending else col.asc())


def _ilike_stmt(stmt: Select, model: type, q: str, fields: Sequence[str]) -> Select:
    cols = [getattr(model, f) for f in fields]
    return stmt.where(or_(*[c.ilike(f"%{q}%") for c in cols]))


def _fuzzy_stmt(stmt: Select, model: type, q: str, fields: Sequence[str]) -> Select:
    """Похожие результаты через `pg_trgm` (расширение подключено в
    ``migrations/versions/0006_pg_trgm.py``) — сортировка по убыванию похожести
    ЗАМЕНЯЕТ любую ранее заданную (в этом фоллбэке порядок и есть смысл поиска:
    самое похожее должно быть первым)."""
    cols = [getattr(model, f) for f in fields]
    sims = [func.similarity(c, q) for c in cols]
    best = sims[0] if len(sims) == 1 else func.greatest(*sims)
    return stmt.where(or_(*[s > 0.3 for s in sims])).order_by(best.desc())


async def paginate_search(
    session: AsyncSession,
    stmt: Select,
    model: type,
    mapper: Callable[[M], S],
    *,
    limit: int,
    offset: int,
    q: str | None = None,
    search_fields: Sequence[str] = (),
    fuzzy_fields: Sequence[str] | None = None,
) -> tuple[list[S], int, bool]:
    """Как :func:`paginate`, плюс текстовый поиск (``q``) с автофоллбэком на fuzzy.

    Без ``q`` — обычная страница ``stmt`` (сортировка/фильтры роута не трогаются).
    С ``q`` — сперва точный ``ILIKE '%q%'`` по ``search_fields``; если он не
    нашёл НИ ОДНОЙ строки и заданы ``fuzzy_fields`` — повтор через
    `pg_trgm`-similarity (fallback, не параллельный поиск — решение зафиксировано
    в IMPLEMENTATION_PLAN.md §0.5).

    :arg stmt: базовый select (без ``limit``/``offset``), с уже применённым
        ``order_by`` (см. :func:`apply_sort`) — fuzzy-фоллбэк это переопределит.
    :arg model: ORM-модель для поисковых колонок.
    :arg search_fields: поля для точного ``ILIKE`` (обычно то же, что и fuzzy).
    :arg fuzzy_fields: поля для similarity-фоллбэка (``None`` — фоллбэка нет).
    """
    if not q or not search_fields:
        return await paginate(session, stmt, mapper, limit=limit, offset=offset)

    exact_stmt = _ilike_stmt(stmt, model, q, search_fields)
    items, total, has_more = await paginate(
        session, exact_stmt, mapper, limit=limit, offset=offset
    )
    if total > 0 or not fuzzy_fields:
        return items, total, has_more

    fuzzy_stmt = _fuzzy_stmt(stmt, model, q, fuzzy_fields)
    return await paginate(session, fuzzy_stmt, mapper, limit=limit, offset=offset)


__all__ = [
    "PageParams",
    "page_params",
    "paginate",
    "paginate_rows",
    "q_param",
    "sort_param",
    "apply_sort",
    "paginate_search",
]
