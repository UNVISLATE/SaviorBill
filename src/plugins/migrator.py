"""Подсистема SQL-миграций и изоляции схем PostgreSQL для плагинов ядра."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger("plugins.migrator")

SLUG_PATTERN = re.compile(r"^[a-z0-9_-]{2,64}$")


class PluginMigrator:
    """Управление изолированными схемами PostgreSQL (plugin_{slug}) и миграциями."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.sm = sessionmaker

    def sanitize_slug(self, slug: str) -> str:
        """Валидация slug плагина для безопасной подстановки в имена схем."""
        clean = slug.strip().lower()
        if not SLUG_PATTERN.match(clean):
            raise ValueError(
                f"Invalid plugin slug: '{slug}'. Must be 2-64 alphanumeric chars, hyphens or underscores."
            )
        return clean.replace("-", "_")

    async def init_migration_table(self) -> None:
        """Создать системную таблицу учёта миграций плагинов в public, если не создана."""
        ddl = """
        CREATE TABLE IF NOT EXISTS public.plugin_migrations (
            id SERIAL PRIMARY KEY,
            plugin_slug VARCHAR(64) NOT NULL,
            migration_file VARCHAR(255) NOT NULL,
            checksum VARCHAR(64) NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(plugin_slug, migration_file)
        );
        """
        async with self.sm() as session:
            await session.execute(text(ddl))
            await session.commit()

    async def apply_migrations(self, slug: str, migrations_dir: Path) -> list[str]:
        """Применить все новые .sql миграции плагина в изолированной схеме plugin_{slug}."""
        slug = self.sanitize_slug(slug)
        schema_name = f"plugin_{slug}"

        await self.init_migration_table()

        if not migrations_dir.exists() or not migrations_dir.is_dir():
            # Если папки миграций нет, просто гарантируем наличие схемы
            async with self.sm() as session:
                await session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}";'))
                await session.commit()
            return []

        # Собираем и сортируем .sql файлы (например, 001_initial.sql, 002_add_index.sql)
        sql_files = sorted(
            [f for f in migrations_dir.iterdir() if f.is_file() and f.suffix == ".sql"],
            key=lambda x: x.name,
        )

        applied: list[str] = []

        async with self.sm() as session:
            # 1. Гарантируем наличие схемы плагина
            await session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}";'))

            # 2. Получаем список уже применённых миграций для этого плагина
            res = await session.execute(
                text(
                    "SELECT migration_file, checksum FROM public.plugin_migrations WHERE plugin_slug = :slug"
                ),
                {"slug": slug},
            )
            applied_map = {row[0]: row[1] for row in res.fetchall()}

            # 3. Применяем новые миграции
            for f in sql_files:
                filename = f.name
                content = f.read_text(encoding="utf-8")
                checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()

                if filename in applied_map:
                    if applied_map[filename] != checksum:
                        logger.warning(
                            f"Migration {filename} for plugin '{slug}' was modified after being applied!"
                        )
                    continue

                logger.info(f"Applying migration '{filename}' for plugin '{slug}' in schema '{schema_name}'...")

                # Устанавливаем search_path на схему плагина с fallback на public
                await session.execute(text(f'SET LOCAL search_path TO "{schema_name}", public;'))

                # Исполняем SQL файл миграции по отдельным выражениям (для совместимости с asyncpg)
                statements = [s.strip() for s in content.split(";") if s.strip()]
                for stmt in statements:
                    await session.execute(text(stmt))

                # Записываем в реестр применённых миграций
                await session.execute(
                    text(
                        """
                        INSERT INTO public.plugin_migrations (plugin_slug, migration_file, checksum)
                        VALUES (:slug, :filename, :checksum);
                        """
                    ),
                    {"slug": slug, "filename": filename, "checksum": checksum},
                )
                applied.append(filename)

            await session.commit()

        return applied

    async def get_schema_size(self, slug: str) -> dict[str, Any]:
        """Получить объём дискового пространства, занимаемый схемой плагина в БД."""
        slug = self.sanitize_slug(slug)
        schema_name = f"plugin_{slug}"

        query = text(
            """
            SELECT 
                COALESCE(SUM(pg_total_relation_size(c.oid)), 0)::bigint AS bytes,
                pg_size_pretty(COALESCE(SUM(pg_total_relation_size(c.oid)), 0)) AS pretty
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = :schema_name;
            """
        )
        async with self.sm() as session:
            res = await session.execute(query, {"schema_name": schema_name})
            row = res.mappings().one()
            return {"bytes": row["bytes"], "pretty": row["pretty"]}

    async def drop_schema_data(self, slug: str) -> None:
        """Полная очистка данных плагина: DROP SCHEMA plugin_{slug} CASCADE."""
        slug = self.sanitize_slug(slug)
        schema_name = f"plugin_{slug}"

        async with self.sm() as session:
            await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE;'))
            await session.execute(
                text("DELETE FROM public.plugin_migrations WHERE plugin_slug = :slug;"),
                {"slug": slug},
            )
            # Удаляем настройки плагина из public.system_settings
            await session.execute(
                text("DELETE FROM public.system_settings WHERE key LIKE :prefix;"),
                {"prefix": f"plugin.{slug}.%"},
            )
            await session.commit()
            logger.info(f"Dropped schema '{schema_name}' and associated plugin settings.")


__all__ = ["PluginMigrator"]
