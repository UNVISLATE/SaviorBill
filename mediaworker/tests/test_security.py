"""Юнит-тесты валидации access-JWT mediaworker."""

import time

import jwt
import pytest

import security

_SECRET = "test-secret-please-change-32chars!!"
_ALG = "HS256"
_ISS = "saviorbill"


def _make(sub, typ="access", ttl=60, **extra):
    now = int(time.time())
    payload = {
        "sub": str(sub),
        "typ": typ,
        "jti": "abc",
        "iat": now,
        "exp": now + ttl,
        "iss": _ISS,
    }
    payload.update(extra)
    return jwt.encode(payload, _SECRET, algorithm=_ALG)


def test_valid_access_returns_id():
    token = _make(42)
    assert security.account_id(token, _SECRET, _ALG, _ISS) == 42


def test_refresh_rejected():
    token = _make(42, typ="refresh")
    with pytest.raises(security.InvalidToken):
        security.account_id(token, _SECRET, _ALG, _ISS)


def test_bad_signature_rejected():
    token = _make(42)
    with pytest.raises(security.InvalidToken):
        security.account_id(token, "wrong-secret", _ALG, _ISS)


def test_expired_rejected():
    token = _make(42, ttl=-10)
    with pytest.raises(security.InvalidToken):
        security.account_id(token, _SECRET, _ALG, _ISS)
