"""Хэширование и проверка паролей на argon2id."""

import secrets
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# Параметры по умолчанию у argon2-cffi — argon2id, разумные для веб-нагрузки.
_ph = PasswordHasher()

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


__all__ = ["hash_pass", "verify_pass", "needs_rehash", "dummy_hash"]
