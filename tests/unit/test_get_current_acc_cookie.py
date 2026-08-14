"""Юнит-тесты cookie-фолбэка для ``get_current_acc``/``get_current_acc_optional``."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from core.config import AppConfig
from dependencies.auth import get_current_acc, get_current_acc_optional
from security.sec import jwt as jwtu
from security.sec.cookies import ACCESS_COOKIE

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


class _FakeRequest:
    def __init__(self, cfg: AppConfig, cookies: dict[str, str] | None = None) -> None:
        self.app = SimpleNamespace(state=SimpleNamespace(settings=cfg))
        self.cookies = cookies or {}


class _FakeMngr:
    def __init__(self, acc) -> None:
        self._acc = acc

    async def by_id(self, acc_id: int):
        return self._acc if self._acc is not None and self._acc.id == acc_id else None


def _cfg(keypair) -> AppConfig:
    private_key, public_key = keypair
    return AppConfig(
        JWT_PRIVATE_KEY=private_key,
        JWT_PUBLIC_KEY=public_key,
        JWT_KID=KID,
        JWT_ALG=ALG,
        JWT_ISS=ISS,
    )


def _access_token(cfg: AppConfig, sub: str = "1") -> str:
    return jwtu.make_access(sub, cfg.JWT_PRIVATE_KEY, cfg.JWT_ALG, ttl=60, iss=cfg.JWT_ISS, kid=cfg.JWT_KID)


async def test_falls_back_to_cookie_when_no_bearer(keypair):
    cfg = _cfg(keypair)
    token = _access_token(cfg)
    acc = SimpleNamespace(id=1)
    request = _FakeRequest(cfg, cookies={ACCESS_COOKIE: token})

    result = await get_current_acc(request, cred=None, mngr=_FakeMngr(acc))
    assert result is acc


async def test_bearer_header_takes_priority_over_cookie(keypair):
    cfg = _cfg(keypair)
    header_token = _access_token(cfg, sub="1")
    cookie_token = "not-a-real-jwt"
    acc = SimpleNamespace(id=1)
    request = _FakeRequest(cfg, cookies={ACCESS_COOKIE: cookie_token})
    cred = SimpleNamespace(credentials=header_token)

    result = await get_current_acc(request, cred=cred, mngr=_FakeMngr(acc))
    assert result is acc


async def test_no_bearer_no_cookie_raises_401(keypair):
    cfg = _cfg(keypair)
    request = _FakeRequest(cfg, cookies={})
    with pytest.raises(HTTPException) as exc_info:
        await get_current_acc(request, cred=None, mngr=_FakeMngr(None))
    assert exc_info.value.status_code == 401


async def test_optional_returns_none_without_bearer_or_cookie(keypair):
    cfg = _cfg(keypair)
    request = _FakeRequest(cfg, cookies={})
    result = await get_current_acc_optional(request, cred=None, mngr=_FakeMngr(None))
    assert result is None


async def test_optional_uses_cookie_fallback(keypair):
    cfg = _cfg(keypair)
    token = _access_token(cfg)
    acc = SimpleNamespace(id=1)
    request = _FakeRequest(cfg, cookies={ACCESS_COOKIE: token})
    result = await get_current_acc_optional(request, cred=None, mngr=_FakeMngr(acc))
    assert result is acc
