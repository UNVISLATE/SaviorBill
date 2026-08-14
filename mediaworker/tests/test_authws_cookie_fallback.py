"""Юнит-тесты фолбэка WS-хендшейка mediaworker на cookie ``sb_access``."""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import utils.security as security
from utils.authctx import ACCESS_COOKIE
from utils.authws import authenticate_ws_payload

pytestmark = pytest.mark.asyncio

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


def _token(sub="1", ttl=60) -> str:
    now = int(time.time())
    payload = {
        "sub": str(sub),
        "typ": "access",
        "jti": "abc",
        "iat": now,
        "exp": now + ttl,
        "iss": _ISS,
        "aud": security.AUDIENCE,
    }
    return jwt.encode(payload, _PRIVATE_KEY, algorithm=_ALG, headers={"kid": _KID})


class _FakeWS:
    def __init__(self, *, frame: dict, cookies: dict[str, str] | None = None) -> None:
        self._frame = json.dumps(frame)
        self.cookies = cookies or {}
        self.closed_code: int | None = None
        self.app = SimpleNamespace(
            state=SimpleNamespace(
                cfg=SimpleNamespace(
                    jwt_public_keys=lambda: {_KID: _PUBLIC_KEY},
                    jwt_alg=_ALG,
                    jwt_iss=_ISS,
                )
            )
        )

    async def receive_text(self) -> str:
        return self._frame

    async def close(self, code: int) -> None:
        self.closed_code = code


async def test_uses_token_from_frame_when_present():
    ws = _FakeWS(frame={"token": _token(), "watch": ["t1"]})
    result = await authenticate_ws_payload(ws)
    assert result is not None
    acc_id, payload = result
    assert acc_id == 1
    assert payload["watch"] == ["t1"]


async def test_falls_back_to_cookie_when_frame_has_no_token():
    ws = _FakeWS(frame={"watch": ["t1"]}, cookies={ACCESS_COOKIE: _token()})
    result = await authenticate_ws_payload(ws)
    assert result is not None
    acc_id, _ = result
    assert acc_id == 1


async def test_no_token_and_no_cookie_closes_connection():
    ws = _FakeWS(frame={"watch": ["t1"]})
    result = await authenticate_ws_payload(ws)
    assert result is None
    assert ws.closed_code == 4401


async def test_invalid_cookie_token_closes_connection():
    ws = _FakeWS(frame={}, cookies={ACCESS_COOKIE: "not-a-jwt"})
    result = await authenticate_ws_payload(ws)
    assert result is None
    assert ws.closed_code == 4401
