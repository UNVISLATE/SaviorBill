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

    async def ping(self) -> None:
        """Проверка готовности для ``/health/ready`` — падает, если пул недоступен."""
        assert self.pool is not None
        await self.pool.fetchval("SELECT 1")

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

    async def setting(self, key: str) -> str | None:
        """Значение настройки из общей (billing) таблицы ``settings``.

        Только не-секретные значения (``is_secret=false``) — mediaworker не
        владеет ключом шифрования (``SecBox``), поэтому секретную настройку
        расшифровать не сможет; в этом случае возвращает ``None`` (fallback
        на .env — см. ``utils/settings.py::SettingsResolver``).
        """
        assert self.pool is not None
        row = await self.pool.fetchrow(
            "SELECT value, is_secret FROM settings WHERE key = $1", key
        )
        if row is None or row["value"] is None or row["is_secret"]:
            return None
        return row["value"]

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

    async def media_variants(self, token: str) -> dict | None:
        """Статус + физические варианты (``main``/``thumb``/``previews``) медиа.

        Fallback-источник для ``serve()``, когда Valkey-кэш ``media:file:*``
        утрачен (например, dev-Valkey без персистентности — ``--save ""
        --appendonly no``, см. ``deploy/dev/docker-compose.yml`` — любой
        рестарт стека обнуляет весь Valkey, хотя файлы на диске и запись в
        Postgres целы). billing — единственный писатель ``variants`` (JSON),
        здесь только чтение.
        """
        assert self.pool is not None
        row = await self.pool.fetchrow(
            "SELECT status, mime, variants FROM system_media WHERE token = $1",
            token,
        )
        if row is None:
            return None
        variants = row["variants"]
        if isinstance(variants, str):
            variants = json.loads(variants) if variants else {}
        return {"status": row["status"], "mime": row["mime"], "variants": variants or {}}

    async def media_count_for_owner(self, owner_id: int) -> int:
        """Число медиа-файлов, принадлежащих аккаунту (для лимита user.media.limit)."""
        assert self.pool is not None
        return await self.pool.fetchval(
            "SELECT count(*) FROM system_media WHERE owner_id = $1", owner_id
        )


__all__ = ["DB", "Account"]
