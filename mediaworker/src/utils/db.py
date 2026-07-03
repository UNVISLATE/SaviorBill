"""Прямой доступ mediaworker к Postgres (asyncpg) — только чтение.

Домену медиа нужно прочитать роль/права аккаунта (авторизация загрузки) и
владельца медиа (проверка прав на ручное превью). Запись готового медиа в БД
делает billing — здесь только SELECT'ы, чтобы не дублировать логику записи в
двух сервисах. Схемой БД владеет billing (таблицы ``accounts``, ``roles``,
``system_media``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import asyncpg


@dataclass(slots=True)
class Account:
    """Минимум сведений об аккаунте для авторизации загрузки."""

    id: int
    perms: dict | None
    role_key: str | None


class DB:
    """Пул подключений к Postgres и медиа-запросы (read-only)."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=5)

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def account(self, acc_id: int) -> Account | None:
        """Аккаунт с правами его роли (или ``None``, если не найден)."""
        assert self.pool is not None
        row = await self.pool.fetchrow(
            "SELECT a.id, r.perms, r.key AS role_key "
            "FROM accounts a LEFT JOIN roles r ON a.role_id = r.id "
            "WHERE a.id = $1",
            acc_id,
        )
        if row is None:
            return None
        perms = row["perms"]
        if isinstance(perms, str):
            perms = json.loads(perms) if perms else None
        return Account(id=row["id"], perms=perms, role_key=row["role_key"])

    async def media_owner(self, token: str) -> tuple[int, int | None, str] | None:
        """(id, owner_id, kind) записи медиа по токену или ``None``."""
        assert self.pool is not None
        row = await self.pool.fetchrow(
            "SELECT id, owner_id, kind FROM system_media WHERE token = $1",
            token,
        )
        if row is None:
            return None
        return row["id"], row["owner_id"], row["kind"]


__all__ = ["DB", "Account"]
