"""Юнит-тесты безопасности паролей (argon2id)."""

import pytest

from security.sec.pwd import hash_pass, needs_rehash, verify_pass

pytestmark = pytest.mark.unit


def test_hash_is_not_plaintext_and_salted():
    h1 = hash_pass("secret123")
    h2 = hash_pass("secret123")
    # Хэш не равен паролю и солится: два хэша одного пароля различаются.
    assert h1 != "secret123"
    assert h1 != h2
    assert h1.startswith("$argon2id$")


def test_verify_correct_and_wrong():
    h = hash_pass("correct horse")
    assert verify_pass(h, "correct horse") is True
    assert verify_pass(h, "wrong") is False


def test_verify_does_not_raise_on_garbage():
    # Кривой хэш не должен ронять приложение исключением.
    assert verify_pass("not-a-hash", "whatever") is False


def test_needs_rehash_false_for_fresh_hash():
    assert needs_rehash(hash_pass("x")) is False
    assert needs_rehash("garbage") is True
