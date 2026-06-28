"""Хэширование и проверка паролей на argon2id."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# Параметры по умолчанию у argon2-cffi — argon2id, разумные для веб-нагрузки.
_ph = PasswordHasher()


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


__all__ = ["hash_pass", "verify_pass", "needs_rehash"]
