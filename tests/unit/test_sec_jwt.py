"""Юнит-тесты JWT (выпуск/валидация access и refresh)."""

import time

import pytest

from utils.sec.jwt import (
    ACCESS,
    REFRESH,
    InvalidJWT,
    decode_jwt,
    make_access,
    make_refresh,
)

pytestmark = pytest.mark.unit

SECRET = "unit-secret-0123456789-abcdefghij-xyz"
ALG = "HS256"
ISS = "saviorbill-test"


def test_access_roundtrip_with_extra_claims():
    tok = make_access("42", SECRET, ALG, ttl=60, iss=ISS, extra={"login": "alice"})
    claims = decode_jwt(tok, SECRET, ALG, ISS)
    assert claims.sub == "42"
    assert claims.typ == ACCESS
    assert claims.extra["login"] == "alice"
    assert claims.jti  # есть уникальный идентификатор


def test_refresh_has_no_extra():
    tok = make_refresh("7", SECRET, ALG, ttl=60, iss=ISS)
    claims = decode_jwt(tok, SECRET, ALG, ISS)
    assert claims.typ == REFRESH
    assert claims.extra == {}


def test_wrong_secret_rejected():
    tok = make_access("1", SECRET, ALG, ttl=60, iss=ISS)
    # Тот же размер, что и SECRET (>=32 байт) — иначе PyJWT предупреждает про
    # короткий HMAC-ключ (InsecureKeyLengthWarning), хотя для теста важен
    # только сам факт несовпадения секретов, а не его длина.
    with pytest.raises(InvalidJWT):
        decode_jwt(tok, "other-secret-0123456789-abcdefghij-zzz", ALG, ISS)


def test_wrong_issuer_rejected():
    tok = make_access("1", SECRET, ALG, ttl=60, iss=ISS)
    with pytest.raises(InvalidJWT):
        decode_jwt(tok, SECRET, ALG, "someone-else")


def test_expired_token_rejected():
    tok = make_access("1", SECRET, ALG, ttl=-1, iss=ISS)
    time.sleep(0.01)
    with pytest.raises(InvalidJWT):
        decode_jwt(tok, SECRET, ALG, ISS)
