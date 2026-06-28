"""Юнит-тесты HMAC-подписи (платёжные колбэки)."""

import pytest

from utils.sec.sign import sign_data, verify_signature

pytestmark = pytest.mark.unit

KEY = b"callback-secret"


def test_sign_is_deterministic_hex():
    s1 = sign_data(KEY, b"1:ext:1")
    s2 = sign_data(KEY, b"1:ext:1")
    assert s1 == s2
    assert len(s1) == 64  # sha256 hex


def test_verify_valid():
    data = b"2:pay_2:1"
    assert verify_signature(KEY, data, sign_data(KEY, data)) is True


def test_verify_rejects_tampered_data():
    sig = sign_data(KEY, b"2:pay_2:1")
    assert verify_signature(KEY, b"2:pay_2:0", sig) is False


def test_verify_rejects_wrong_key():
    sig = sign_data(KEY, b"x")
    assert verify_signature(b"other", b"x", sig) is False
