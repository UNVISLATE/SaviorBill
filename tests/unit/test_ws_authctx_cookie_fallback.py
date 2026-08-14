"""Юнит-тесты фолбэка WS-хендшейка billing на cookie ``sb_access`` (Фаза 5, п.1)."""

from __future__ import annotations

import contextlib
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import apiws.authctx as authctx
from security.sec import jwt as jwtu
from security.sec.cookies import ACCESS_COOKIE

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

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


_PRIVATE_KEY, _PUBLIC_KEY = _keypair()


def _token(sub: str = "1") -> str:
    return jwtu.make_access(sub, _PRIVATE_KEY, ALG, ttl=60, iss=ISS, kid=KID)


class _FakeValkey:
    async def incr(self, key: str) -> int:
        return 1

    async def expire(self, key: str, ttl: int) -> None:
        return None

    async def decr(self, key: str) -> int:
        return 0


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeUserMngr:
    def __init__(self, _session) -> None:
        pass

    async def by_id(self, acc_id: int):
        return SimpleNamespace(id=acc_id) if acc_id == 1 else None


class _FakeWS:
    def __init__(self, *, frame: dict, cookies: dict[str, str] | None = None) -> None:
        import json

        self._frame = json.dumps(frame)
        self.cookies = cookies or {}
        self.client = SimpleNamespace(host="1.2.3.4")
        self.closed_code: int | None = None
        self.app = SimpleNamespace(
            state=SimpleNamespace(
                valkey=_FakeValkey(),
                settings=SimpleNamespace(
                    WS_PREAUTH_MAX_PER_IP=10,
                    WS_MAX_FRAME_BYTES=4096,
                    WS_HANDSHAKE_TIMEOUT_SEC=5,
                    JWT_ALG=ALG,
                    JWT_ISS=ISS,
                    jwt_public_keys=lambda: {KID: _PUBLIC_KEY},
                ),
                db_sessionmaker=lambda: _FakeSession(),
            )
        )

    async def receive(self) -> dict:
        return {"type": "websocket.receive", "text": self._frame}

    async def close(self, code: int) -> None:
        self.closed_code = code


@pytest.fixture(autouse=True)
def _patch_user_mngr(monkeypatch):
    monkeypatch.setattr(authctx, "UserMngr", _FakeUserMngr)


async def test_authenticate_ws_uses_frame_token():
    ws = _FakeWS(frame={"token": _token()})
    result = await authctx.authenticate_ws(ws)
    assert result is not None
    acc, exp = result
    assert acc.id == 1
    assert exp > 0


async def test_authenticate_ws_falls_back_to_cookie():
    ws = _FakeWS(frame={}, cookies={ACCESS_COOKIE: _token()})
    result = await authctx.authenticate_ws(ws)
    assert result is not None
    acc, _ = result
    assert acc.id == 1


async def test_authenticate_ws_no_token_no_cookie_closes():
    ws = _FakeWS(frame={})
    result = await authctx.authenticate_ws(ws)
    assert result is None
    assert ws.closed_code == 4401
