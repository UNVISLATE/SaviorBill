"""Юнит-тесты JWT (выпуск/валидация access и refresh, RS256, key ring)."""

from __future__ import annotations

import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from security.sec.jwt import (
    ACCESS,
    REFRESH,
    InvalidJWT,
    decode_jwt,
    make_access,
    make_refresh,
)

pytestmark = pytest.mark.unit

ALG = "RS256"
ISS = "saviorbill-test"
KID = "kid-1"


def _keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


@pytest.fixture(scope="module")
def keypair() -> tuple[str, str]:
    return _keypair()


def test_access_roundtrip_with_extra_claims(keypair):
    private_key, public_key = keypair
    tok = make_access("42", private_key, ALG, ttl=60, iss=ISS, kid=KID, extra={"login": "alice"})
    claims = decode_jwt(tok, {KID: public_key}, ALG, ISS)
    assert claims.sub == "42"
    assert claims.typ == ACCESS
    assert claims.extra["login"] == "alice"
    assert claims.jti  # есть уникальный идентификатор


def test_refresh_has_no_extra(keypair):
    private_key, public_key = keypair
    tok = make_refresh("7", private_key, ALG, ttl=60, iss=ISS, kid=KID)
    claims = decode_jwt(tok, {KID: public_key}, ALG, ISS)
    assert claims.typ == REFRESH
    assert claims.extra == {}


def test_unknown_kid_rejected(keypair):
    """Ключ есть, но токен подписан не им — kid не совпадает ни с одним в key ring."""
    private_key, _public_key = keypair
    tok = make_access("1", private_key, ALG, ttl=60, iss=ISS, kid=KID)
    _other_private, other_public = _keypair()
    with pytest.raises(InvalidJWT):
        decode_jwt(tok, {"some-other-kid": other_public}, ALG, ISS)


def test_wrong_key_for_kid_rejected(keypair):
    """kid совпадает, но за ним в key ring лежит чужой публичный ключ (ключ ротирован
    некорректно/повреждён) — подпись всё равно не проходит."""
    private_key, _public_key = keypair
    tok = make_access("1", private_key, ALG, ttl=60, iss=ISS, kid=KID)
    _other_private, other_public = _keypair()
    with pytest.raises(InvalidJWT):
        decode_jwt(tok, {KID: other_public}, ALG, ISS)


def test_key_ring_verifies_previous_kid_during_grace_period(keypair):
    """Токен, выпущенный предыдущим ключом, всё ещё проходит, пока он в key ring."""
    private_key, public_key = keypair
    other_private, other_public = _keypair()
    tok = make_access("1", private_key, ALG, ttl=60, iss=ISS, kid=KID)
    claims = decode_jwt(tok, {KID: public_key, "kid-2": other_public}, ALG, ISS)
    assert claims.sub == "1"


def test_wrong_issuer_rejected(keypair):
    private_key, public_key = keypair
    tok = make_access("1", private_key, ALG, ttl=60, iss=ISS, kid=KID)
    with pytest.raises(InvalidJWT):
        decode_jwt(tok, {KID: public_key}, ALG, "someone-else")


def test_expired_token_rejected(keypair):
    private_key, public_key = keypair
    tok = make_access("1", private_key, ALG, ttl=-1, iss=ISS, kid=KID)
    time.sleep(0.01)
    with pytest.raises(InvalidJWT):
        decode_jwt(tok, {KID: public_key}, ALG, ISS)


def test_disallowed_alg_rejected_on_encode(keypair):
    private_key, _public_key = keypair
    with pytest.raises(InvalidJWT):
        make_access("1", private_key, "none", ttl=60, iss=ISS, kid=KID)


def test_disallowed_alg_rejected_on_decode(keypair):
    private_key, public_key = keypair
    tok = make_access("1", private_key, ALG, ttl=60, iss=ISS, kid=KID)
    with pytest.raises(InvalidJWT):
        decode_jwt(tok, {KID: public_key}, "none", ISS)


def test_missing_typ_rejected(keypair):
    """Токен без ``typ`` (например, подписанный тем же ключом для другой цели)
    не должен молча трактоваться как access."""
    import jwt as pyjwt

    private_key, public_key = keypair
    payload = {
        "sub": "1",
        "jti": "x",
        "iat": int(time.time()),
        "exp": int(time.time()) + 60,
        "iss": ISS,
        "aud": "saviorbill-services",
    }
    tok = pyjwt.encode(payload, private_key, algorithm=ALG, headers={"kid": KID})
    with pytest.raises(InvalidJWT):
        decode_jwt(tok, {KID: public_key}, ALG, ISS)


def test_unknown_typ_rejected(keypair):
    import jwt as pyjwt

    private_key, public_key = keypair
    payload = {
        "sub": "1",
        "typ": "totally-not-a-real-type",
        "jti": "x",
        "iat": int(time.time()),
        "exp": int(time.time()) + 60,
        "iss": ISS,
        "aud": "saviorbill-services",
    }
    tok = pyjwt.encode(payload, private_key, algorithm=ALG, headers={"kid": KID})
    with pytest.raises(InvalidJWT):
        decode_jwt(tok, {KID: public_key}, ALG, ISS)


def test_token_carries_fixed_audience(keypair):
    """``aud`` присутствует и не настраивается извне — фиксированная аудитория стека."""
    import jwt as pyjwt

    private_key, public_key = keypair
    tok = make_access("1", private_key, ALG, ttl=60, iss=ISS, kid=KID)
    raw = pyjwt.decode(tok, public_key, algorithms=[ALG], options={"verify_aud": False})
    assert raw["aud"] == "saviorbill-services"
