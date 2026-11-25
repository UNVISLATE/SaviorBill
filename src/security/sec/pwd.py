"""Хэширование и проверка паролей на argon2id."""

import asyncio
import os
import secrets
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# Параметры по умолчанию у argon2-cffi — argon2id, разумные для веб-нагрузки.
_ph = PasswordHasher()

# Ограничиваем число одновременных Argon2id-операций в threadpool, чтобы под
# флудом не уйти в OOM (каждый вызов аллоцирует ~64 MiB памяти).
_ARGON2_SEMAPHORE: asyncio.Semaphore | None = None
_ARGON2_CONCURRENCY = max(2, min(8, os.cpu_count() or 2))


def _get_semaphore() -> asyncio.Semaphore:
    global _ARGON2_SEMAPHORE
    if _ARGON2_SEMAPHORE is None:
        _ARGON2_SEMAPHORE = asyncio.Semaphore(_ARGON2_CONCURRENCY)
    return _ARGON2_SEMAPHORE

# Константный "балластный" хэш для анти-тайминг проверки логина: когда
# аккаунт не найден, всё равно гоняем полный verify() против этого хэша,
# чтобы время ответа не отличалось от случая "аккаунт найден, пароль неверен"
_DUMMY_HASH = _ph.hash(secrets.token_hex(32))


def hash_pass(raw: str) -> str:
    """Вернуть argon2id-хэш пароля (соль внутри строки хэша)."""
    return _ph.hash(raw)


def verify_pass(pass_hash: str, raw: str) -> bool:
    """Проверить пароль против сохранённого хэша. Без исключений наружу."""
    try:
        return _ph.verify(pass_hash, raw)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(pass_hash: str) -> bool:
    """Нужно ли перехэшировать (изменились параметры argon2)."""
    try:
        return _ph.check_needs_rehash(pass_hash)
    except (InvalidHashError, ValueError):
        return True


def dummy_hash() -> str:
    """Балластный argon2-хэш для анти-тайминг проверки при отсутствии аккаунта."""
    return _DUMMY_HASH


async def hash_pass_async(raw: str) -> str:
    """Асинхронная обёртка над ``hash_pass`` в ограниченном пуле потоков."""
    async with _get_semaphore():
        return await asyncio.to_thread(hash_pass, raw)


async def verify_pass_async(pass_hash: str, raw: str) -> bool:
    """Асинхронная обёртка над ``verify_pass`` в ограниченном пуле потоков."""
    async with _get_semaphore():
        return await asyncio.to_thread(verify_pass, pass_hash, raw)


__all__ = [
    "hash_pass",
    "verify_pass",
    "hash_pass_async",
    "verify_pass_async",
    "needs_rehash",
    "dummy_hash",
]
