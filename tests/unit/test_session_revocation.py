"""Массовый отзыв сессий аккаунта (AUDIT.md §1.3 SEC-H1/H2)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.auth import TokenSvc

pytestmark = pytest.mark.unit


class _FakeValkey:
    """Мини-Valkey с поддержкой хэшей сессий и scan_iter по префиксу."""

    def __init__(self) -> None:
        self.hashes: dict[str, dict] = {}
        self.strings: dict[str, str] = {}

    async def hgetall(self, key: str) -> dict:
        return self.hashes.get(key, {})

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.strings[key] = value

    async def delete(self, key: str) -> None:
        self.hashes.pop(key, None)
        self.strings.pop(key, None)

    async def exists(self, key: str) -> int:
        return 1 if key in self.strings else 0

    async def eval(self, _script: str, _numkeys: int, key: str, ttl: str) -> int:
        if key in self.strings:
            return 0
        self.strings[key] = "1"
        return 1

    async def scan_iter(self, match: str):
        prefix = match.rstrip("*")
        for key in list(self.hashes):
            if key.startswith(prefix):
                yield key


def _cfg(rsa_keypair):
    priv, pub = rsa_keypair
    kid = "test-kid"
    return SimpleNamespace(
        JWT_PRIVATE_KEY=priv,
        JWT_PUBLIC_KEY=pub,
        JWT_KID=kid,
        JWT_ALG="RS256",
        JWT_ISS="saviorbill",
        ACCESS_TOKEN_TTL=900,
        REFRESH_TOKEN_TTL=86400,
        jwt_public_keys=lambda: {kid: pub},
    )


@pytest.mark.asyncio
async def test_revoke_all_sessions_denylists_every_jti(rsa_keypair):
    vk = _FakeValkey()
    for jti in ("a1", "b2", "c3"):
        vk.hashes[f"session:7:{jti}"] = {"exp": "99999999999"}
    vk.hashes["session:8:other"] = {"exp": "99999999999"}

    svc = TokenSvc(_cfg(rsa_keypair), vk)
    assert await svc.revoke_all_sessions(7) == 3

    for jti in ("a1", "b2", "c3"):
        assert await svc.is_revoked(jti)
        assert f"session:7:{jti}" not in vk.hashes
    # Чужие сессии не тронуты.
    assert "session:8:other" in vk.hashes


@pytest.mark.asyncio
async def test_revoke_all_sessions_on_account_without_sessions(rsa_keypair):
    svc = TokenSvc(_cfg(rsa_keypair), _FakeValkey())
    assert await svc.revoke_all_sessions(42) == 0
