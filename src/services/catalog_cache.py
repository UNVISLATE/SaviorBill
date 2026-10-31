"""Сервис кэширования публичного каталога и сбора метрик Valkey."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi.encoders import jsonable_encoder
import valkey.asyncio as valkey
from utils.degrade import VALKEY_ERRORS, note_degraded

log = logging.getLogger("saviorbill.cache")

KEY_PREFIX_TREE = "cache:catalog:tree"
KEY_PREFIX_SERVICES = "cache:catalog:services"
KEY_STATS_HITS = "cache:stats:hits"
KEY_STATS_MISSES = "cache:stats:misses"
KEY_STATS_INVALIDATIONS = "cache:stats:invalidations"


def _format_bytes(bytes_count: int) -> str:
    """Человекочитаемый формат байтов."""
    if bytes_count < 1024:
        return f"{bytes_count} B"
    kb = bytes_count / 1024
    if kb < 1024:
        return f"{kb:.1f} KB"
    mb = kb / 1024
    if mb < 1024:
        return f"{mb:.2f} MB"
    gb = mb / 1024
    return f"{gb:.2f} GB"


async def get_cached_catalogs(vk: valkey.Valkey) -> list[dict[str, Any]] | None:
    """Получить кэшированное дерево каталогов."""
    try:
        raw = await vk.get(KEY_PREFIX_TREE)
        if raw is not None:
            await vk.incr(KEY_STATS_HITS)
            return json.loads(raw)
        await vk.incr(KEY_STATS_MISSES)
        return None
    except VALKEY_ERRORS as exc:
        note_degraded("cache", exc)
        return None


async def set_cached_catalogs(
    vk: valkey.Valkey, data: list[dict[str, Any]], ttl_sec: int = 180
) -> None:
    """Сохранить дерево каталогов в кэш."""
    try:
        raw = json.dumps(jsonable_encoder(data))
        await vk.set(KEY_PREFIX_TREE, raw, ex=ttl_sec)
    except VALKEY_ERRORS as exc:
        note_degraded("cache", exc)


def _services_key(catalog_id: int | None, limit: int, offset: int) -> str:
    cid = catalog_id if catalog_id is not None else "all"
    return f"{KEY_PREFIX_SERVICES}:{cid}:{limit}:{offset}"


async def get_cached_services(
    vk: valkey.Valkey, catalog_id: int | None, limit: int, offset: int
) -> dict[str, Any] | None:
    """Получить кэшированную страницу услуг."""
    try:
        key = _services_key(catalog_id, limit, offset)
        raw = await vk.get(key)
        if raw is not None:
            await vk.incr(KEY_STATS_HITS)
            return json.loads(raw)
        await vk.incr(KEY_STATS_MISSES)
        return None
    except VALKEY_ERRORS as exc:
        note_degraded("cache", exc)
        return None


async def set_cached_services(
    vk: valkey.Valkey,
    catalog_id: int | None,
    limit: int,
    offset: int,
    data: dict[str, Any],
    ttl_sec: int = 180,
) -> None:
    """Сохранить страницу услуг в кэш."""
    try:
        key = _services_key(catalog_id, limit, offset)
        raw = json.dumps(jsonable_encoder(data))
        await vk.set(key, raw, ex=ttl_sec)
    except VALKEY_ERRORS as exc:
        note_degraded("cache", exc)


async def invalidate_catalog_cache(vk: valkey.Valkey) -> int:
    """Инвалидировать все ключи кэша каталога (дерево и выборки услуг).

    Вызывается при создании/редактировании/удалении каталогов и услуг.
    """
    deleted_count = 0
    try:
        keys_to_del: list[str] = []
        async for k in vk.scan_iter(match="cache:catalog:*", count=100):
            keys_to_del.append(k if isinstance(k, str) else k.decode())
        if keys_to_del:
            deleted_count = await vk.delete(*keys_to_del)
        await vk.incr(KEY_STATS_INVALIDATIONS)
        log.info("catalog cache invalidated: deleted %d keys", deleted_count)
    except VALKEY_ERRORS as exc:
        note_degraded("cache", exc)
    return deleted_count


async def get_cache_stats(vk: valkey.Valkey) -> dict[str, Any]:
    """Собрать полную статистику кэша и использования памяти Valkey."""
    hits = 0
    misses = 0
    invalidations = 0
    used_memory_bytes = 0
    peak_memory_bytes = 0
    total_keys = 0
    valkey_version = "unknown"
    uptime_seconds = 0
    namespaces: list[dict[str, Any]] = []

    try:
        raw_hits = await vk.get(KEY_STATS_HITS)
        raw_misses = await vk.get(KEY_STATS_MISSES)
        raw_inv = await vk.get(KEY_STATS_INVALIDATIONS)
        hits = int(raw_hits or 0)
        misses = int(raw_misses or 0)
        invalidations = int(raw_inv or 0)

        # Valkey info
        mem_info = await vk.info("memory")
        used_memory_bytes = int(mem_info.get("used_memory", 0))
        peak_memory_bytes = int(mem_info.get("used_memory_peak", 0))

        server_info = await vk.info("server")
        valkey_version = server_info.get("valkey_version") or server_info.get("redis_version", "unknown")
        uptime_seconds = int(server_info.get("uptime_in_seconds", 0))

        total_keys = await vk.dbsize()

        # Сканирование префиксов
        tracked_prefixes = [
            ("cache:catalog", "Кэш каталога и услуг"),
            ("rl:", "Счётчики Rate Limit"),
            ("auth:deny", "Отозванные токены и сессии"),
            ("settings", "Кэш системных настроек"),
            ("media:", "Медиа-задачи и файлы"),
            ("lua:", "Стримы и задачи LuaWorker"),
            ("billing:", "Очереди биллинга и планировщик"),
            ("tasklog:", "Журналы выполнения задач"),
            ("proclog:", "Логи обработки задач"),
            ("security", "События безопасности и баны"),
            ("system", "Журналы ошибок и аудит"),
        ]

        for prefix, label in tracked_prefixes:
            count = 0
            async for _ in vk.scan_iter(match=f"{prefix}*", count=200):
                count += 1
            namespaces.append({
                "prefix": prefix,
                "label": label,
                "keys_count": count,
            })

    except VALKEY_ERRORS as exc:
        note_degraded("cache", exc)

    total_requests = hits + misses
    hit_rate = round((hits / total_requests) * 100, 1) if total_requests > 0 else 0.0

    return {
        "hits": hits,
        "misses": misses,
        "hit_rate": hit_rate,
        "invalidations": invalidations,
        "used_memory_bytes": used_memory_bytes,
        "used_memory_human": _format_bytes(used_memory_bytes),
        "peak_memory_bytes": peak_memory_bytes,
        "peak_memory_human": _format_bytes(peak_memory_bytes),
        "total_keys": total_keys,
        "valkey_version": valkey_version,
        "uptime_seconds": uptime_seconds,
        "namespaces": namespaces,
    }


async def flush_cache_data(vk: valkey.Valkey, mode: str = "catalog") -> dict[str, Any]:
    """Очистить кэш в зависимости от режима:

    - 'catalog': удалить только кэш каталога (cache:catalog:*)
    - 'all_cache': удалить все кэшированные данные (cache:*)
    - 'reset_stats': обнулить счётчики hits/misses/invalidations
    """
    deleted_count = 0
    try:
        if mode == "reset_stats":
            await vk.delete(KEY_STATS_HITS, KEY_STATS_MISSES, KEY_STATS_INVALIDATIONS)
            return {"ok": True, "mode": mode, "cleared_keys": 0, "message": "Статистика кэша сброшена"}

        pattern = "cache:catalog:*" if mode == "catalog" else "cache:*"
        keys_to_del: list[str] = []
        async for k in vk.scan_iter(match=pattern, count=100):
            keys_to_del.append(k if isinstance(k, str) else k.decode())
        if keys_to_del:
            deleted_count = await vk.delete(*keys_to_del)

        return {
            "ok": True,
            "mode": mode,
            "cleared_keys": deleted_count,
            "message": f"Успешно удалено {deleted_count} ключей кэша",
        }
    except VALKEY_ERRORS as exc:
        note_degraded("cache", exc)
        return {"ok": False, "mode": mode, "cleared_keys": 0, "error": str(exc)}
