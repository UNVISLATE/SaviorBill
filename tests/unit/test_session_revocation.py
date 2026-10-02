"""Массовый отзыв сессий аккаунта (AUDIT.md §1.3 SEC-H1/H2)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from errors import AuthSessionLimitError
from security.sec import jwt as jwtu
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


@pytest.mark.asyncio
async def test_durable_single_revoke_can_join_audit_transaction(rsa_keypair):
    row = SimpleNamespace(
        revoked_at=None,
        revoke_reason=None,
        refresh_jti_hash="a" * 64,
        session_version=0,
        expires_at=datetime.now(timezone.utc),
    )
    session = SimpleNamespace(scalar=AsyncMock(return_value=row), commit=AsyncMock())
    cfg = _cfg(rsa_keypair)
    cfg.AUTH_SESSION_HASH_KEY = "test-session-hash-key"
    svc = TokenSvc(cfg, _FakeValkey(), session=session)

    assert await svc.revoke_session(7, svc._session_digest("refresh-jti"), commit=False)
    assert row.revoke_reason == "manual"
    session.commit.assert_not_awaited()

    assert await svc.revoke_session(7, svc._session_digest("refresh-jti"))
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_durable_issue_rejects_when_active_session_limit_is_reached(rsa_keypair):
    account = SimpleNamespace(
        id=7, auth_session_version=0, login="user", role=None, is_active=True
    )
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[account, 2]),
        add=lambda _row: None,
        commit=AsyncMock(),
    )
    settings = SimpleNamespace(get_int=AsyncMock(return_value=2))
    cfg = _cfg(rsa_keypair)
    cfg.AUTH_SESSION_HASH_KEY = "test-session-hash-key"
    svc = TokenSvc(cfg, _FakeValkey(), settings=settings, session=session)

    claims = svc._decode_refresh(svc.issue(account).refresh_token)
    with pytest.raises(AuthSessionLimitError):
        await svc._save_session(7, claims, ip=None, user_agent=None, created_at=1)
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_durable_rotation_revokes_old_lineage_in_one_commit(rsa_keypair):
    account = SimpleNamespace(
        id=7,
        auth_session_version=0,
        role=SimpleNamespace(allow_login=True, name="user"),
        login="user",
        is_active=True,
    )
    old = SimpleNamespace(
        created_at=datetime.now(timezone.utc),
        revoked_at=None,
        revoke_reason=None,
        last_seen_at=None,
        replaced_by_id=None,
    )
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=old),
        add=lambda row: setattr(session, "new_row", row),
        flush=AsyncMock(side_effect=lambda: setattr(session.new_row, "id", 99)),
        commit=AsyncMock(),
    )
    cfg = _cfg(rsa_keypair)
    cfg.AUTH_SESSION_HASH_KEY = "test-session-hash-key"
    svc = TokenSvc(cfg, _FakeValkey(), session=session)
    mngr = SimpleNamespace(by_id=AsyncMock(return_value=account))
    old_token = svc.issue(account).refresh_token

    rotated_account, pair = await svc.rotate(
        old_token,
        mngr,
        ip="127.0.0.1",
        user_agent="test-agent",
    )

    assert rotated_account is account
    assert pair.refresh_token
    assert old.revoke_reason == "rotated"
    assert old.replaced_by_id == 99
    session.commit.assert_awaited_once()
    with pytest.raises(HTTPException) as exc_info:
        await svc.rotate(old_token, mngr)
    assert exc_info.value.status_code == 401
    assert mngr.by_id.await_count == 1


def test_durable_access_token_carries_only_opaque_session_handle(rsa_keypair):
    account = SimpleNamespace(
        id=7,
        auth_session_version=0,
        role=SimpleNamespace(name="user"),
        login="user",
        is_active=True,
    )
    cfg = _cfg(rsa_keypair)
    cfg.AUTH_SESSION_HASH_KEY = "test-session-hash-key"
    svc = TokenSvc(cfg, _FakeValkey())

    pair = svc.issue(account)
    claims = jwtu.decode_jwt(
        pair.access_token, cfg.jwt_public_keys(), cfg.JWT_ALG, cfg.JWT_ISS
    )
    assert claims.extra["sid"] == svc._session_digest(
        svc._decode_refresh(pair.refresh_token).jti
    )
    assert len(claims.extra["sid"]) == 64
