"""Юнит-тесты валидации access-JWT mediaworker (RS256, key ring)."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import utils.security as security

_ALG = "RS256"
_ISS = "saviorbill"
_KID = "kid-1"


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


_PRIVATE_KEY, _PUBLIC_KEY = _keypair()


def _make(sub, typ="access", ttl=60, kid=_KID, **extra):
    now = int(time.time())
    payload = {
        "sub": str(sub),
        "typ": typ,
        "jti": "abc",
        "iat": now,
        "exp": now + ttl,
        "iss": _ISS,
        "aud": security.AUDIENCE,
    }
    payload.update(extra)
    headers = {"kid": kid} if kid else None
    return jwt.encode(payload, _PRIVATE_KEY, algorithm=_ALG, headers=headers)


def test_valid_access_returns_id():
    token = _make(42)
    assert security.account_id(token, {_KID: _PUBLIC_KEY}, _ALG, _ISS) == 42


def test_refresh_rejected():
    token = _make(42, typ="refresh")
    with pytest.raises(security.InvalidToken):
        security.account_id(token, {_KID: _PUBLIC_KEY}, _ALG, _ISS)


def test_bad_signature_rejected():
    token = _make(42)
    _other_private, other_public = _keypair()
    with pytest.raises(security.InvalidToken):
        security.account_id(token, {_KID: other_public}, _ALG, _ISS)


def test_unknown_kid_rejected():
    token = _make(42)
    _other_private, other_public = _keypair()
    with pytest.raises(security.InvalidToken):
        security.account_id(token, {"other-kid": other_public}, _ALG, _ISS)


def test_key_ring_verifies_previous_kid():
    """Ключ из предыдущей ротации всё ещё принимается, если он в key ring."""
    token = _make(42, kid=_KID)
    _other_private, other_public = _keypair()
    assert (
        security.account_id(
            token, {_KID: _PUBLIC_KEY, "kid-2": other_public}, _ALG, _ISS
        )
        == 42
    )


def test_expired_rejected():
    token = _make(42, ttl=-10)
    with pytest.raises(security.InvalidToken):
        security.account_id(token, {_KID: _PUBLIC_KEY}, _ALG, _ISS)


def test_disallowed_alg_rejected():
    with pytest.raises(security.InvalidToken):
        security.account_id(_make(42), {_KID: _PUBLIC_KEY}, "none", _ISS)


def test_missing_typ_rejected():
    now = int(time.time())
    payload = {
        "sub": "42",
        "jti": "abc",
        "iat": now,
        "exp": now + 60,
        "iss": _ISS,
        "aud": security.AUDIENCE,
    }
    token = jwt.encode(payload, _PRIVATE_KEY, algorithm=_ALG, headers={"kid": _KID})
    with pytest.raises(security.InvalidToken):
        security.account_id(token, {_KID: _PUBLIC_KEY}, _ALG, _ISS)


def test_wrong_audience_rejected():
    token = _make(42, aud="someone-else")
    with pytest.raises(security.InvalidToken):
        security.account_id(token, {_KID: _PUBLIC_KEY}, _ALG, _ISS)
