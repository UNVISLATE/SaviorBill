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
KEY_PREFIX_IDS = "cache:catalog:ids"
KEY_PREFIX_SERVICE = "cache:catalog:service"
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


# ---------------------------------------------------------
# Двухуровневый кэш: Уровень 1 (Индекс ID каталога)
# ---------------------------------------------------------
def _catalog_ids_key(catalog_id: int | None) -> str:
    cid = catalog_id if catalog_id is not None else "all"
    return f"{KEY_PREFIX_IDS}:{cid}"


async def get_cached_catalog_ids(
    vk: valkey.Valkey, catalog_id: int | None
) -> list[int] | None:
    """Получить упорядоченный список ID активных услуг каталога (Уровень 1)."""
    try:
        key = _catalog_ids_key(catalog_id)
        raw = await vk.get(key)
        if raw is not None:
            await vk.incr(KEY_STATS_HITS)
            return json.loads(raw)
        await vk.incr(KEY_STATS_MISSES)
        return None
    except VALKEY_ERRORS as exc:
        note_degraded("cache", exc)
        return None


async def set_cached_catalog_ids(
    vk: valkey.Valkey,
    catalog_id: int | None,
    ids: list[int],
    ttl_sec: int = 180,
) -> None:
    """Сохранить упорядоченный список ID активных услуг каталога (Уровень 1)."""
    try:
        key = _catalog_ids_key(catalog_id)
        await vk.set(key, json.dumps(ids), ex=ttl_sec)
    except VALKEY_ERRORS as exc:
        note_degraded("cache", exc)


# ---------------------------------------------------------
# Двухуровневый кэш: Уровень 2 (Сущности услуг / карточки)
# ---------------------------------------------------------
def _service_entity_key(service_id: int) -> str:
    return f"{KEY_PREFIX_SERVICE}:{service_id}"


async def get_cached_service_entities(
    vk: valkey.Valkey, service_ids: list[int]
) -> tuple[dict[int, dict[str, Any]], list[int]]:
    """Пакетное чтение сущностей услуг через MGET (Уровень 2).

    Возвращает:
      - found: словарь {service_id: dict_data}
      - missing: список ID, которых нет в кэше Valkey (промах)
    """
    if not service_ids:
        return {}, []

    found: dict[int, dict[str, Any]] = {}
    missing: list[int] = []

    try:
        keys = [_service_entity_key(sid) for sid in service_ids]
        raw_items = await vk.mget(keys)

        hits_count = 0
        misses_count = 0

        for sid, raw in zip(service_ids, raw_items):
            if raw is not None:
                try:
                    found[sid] = json.loads(raw)
                    hits_count += 1
                except (ValueError, TypeError):
                    missing.append(sid)
                    misses_count += 1
            else:
                missing.append(sid)
                misses_count += 1

        if hits_count > 0:
            await vk.incrby(KEY_STATS_HITS, hits_count)
        if misses_count > 0:
            await vk.incrby(KEY_STATS_MISSES, misses_count)

        return found, missing
    except VALKEY_ERRORS as exc:
        note_degraded("cache", exc)
        return {}, list(service_ids)


async def set_cached_service_entities(
    vk: valkey.Valkey,
    entities: dict[int, dict[str, Any]],
    ttl_sec: int = 180,
) -> None:
    """Пакетное сохранение сущностей услуг в кэш Valkey (Уровень 2)."""
    if not entities:
        return

    try:
        pipe = vk.pipeline(transaction=False)
        for sid, data in entities.items():
            key = _service_entity_key(sid)
            raw = json.dumps(jsonable_encoder(data))
            pipe.set(key, raw, ex=ttl_sec)
        await pipe.execute()
    except VALKEY_ERRORS as exc:
        note_degraded("cache", exc)


# ---------------------------------------------------------
# Инвалидация кэша: точечная и глобальная
# ---------------------------------------------------------
async def invalidate_service_entity(vk: valkey.Valkey, service_id: int) -> int:
    """Точечно удалить сущность услуги из кэша (при смене цены, остатка ключей, фото)."""
    try:
        key = _service_entity_key(service_id)
        deleted = await vk.delete(key)
        await vk.incr(KEY_STATS_INVALIDATIONS)
        log.info("service entity cache invalidated: service_id=%d", service_id)
        return deleted
    except VALKEY_ERRORS as exc:
        note_degraded("cache", exc)
        return 0


async def invalidate_catalog_indexes(vk: valkey.Valkey) -> int:
    """Сбросить списки ID каталога (при создании/удалении услуг или смене категорий)."""
    try:
        keys_to_del: list[str] = []
        async for k in vk.scan_iter(match=f"{KEY_PREFIX_IDS}:*", count=100):
            keys_to_del.append(k if isinstance(k, str) else k.decode())
        deleted = 0
        if keys_to_del:
            deleted = await vk.delete(*keys_to_del)
        await vk.incr(KEY_STATS_INVALIDATIONS)
        return deleted
    except VALKEY_ERRORS as exc:
        note_degraded("cache", exc)
        return 0


async def invalidate_catalog_cache(vk: valkey.Valkey) -> int:
    """Полная инвалидация кэша каталога (дерево, индексы ID и все сущности услуг)."""
    deleted_count = 0
    try:
        keys_to_del: list[str] = []
        async for k in vk.scan_iter(match="cache:catalog:*", count=100):
            keys_to_del.append(k if isinstance(k, str) else k.decode())
        if keys_to_del:
            deleted_count = await vk.delete(*keys_to_del)
        await vk.incr(KEY_STATS_INVALIDATIONS)
        log.info("catalog cache fully invalidated: deleted %d keys", deleted_count)
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
