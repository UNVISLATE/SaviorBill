from typing import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.engine.url import URL


def create_db_engine(
    db_dsn: str | URL,
    *,
    pool_size: int = 20,
    max_overflow: int = 30,
    pool_timeout: int = 30,
    pool_recycle: int = 1800,
    **kwargs,
) -> AsyncEngine:
    """Создать новый асинхронный движок SQLAlchemy с настроенным пулом соединений."""
    dsn_str = str(db_dsn)
    if "sqlite" in dsn_str:
        return create_async_engine(db_dsn, echo=False, future=True, **kwargs)
    return create_async_engine(
        db_dsn,
        echo=False,
        future=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        **kwargs,
    )


def create_db_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Создать новый асинхронный `sessionmaker` SQLAlchemy."""
    return async_sessionmaker(bind=engine, expire_on_commit=False)


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Получить сессию БД из `app.state`."""
    async with request.app.state.db_sessionmaker() as session:
        yield session
