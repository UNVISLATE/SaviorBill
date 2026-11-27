"""Юнит-тесты Stage 3: 2FA без пароля, email-сброс, история email, privacy.* и GDPR."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api.v1.user.gdpr import _cooldown_remaining_sec
from api.v1.user.twofa import twofa_disable, twofa_email_reset_request
from schemas.auth import TwoFADisable
from security.owner_guard import assert_can_reset_twofa, is_staff_account
from utils.datetime_utils import utc_now

pytestmark = pytest.mark.unit


def _make_role(key: str, *, protected: bool = False, admin_login: bool = False, perms: dict | None = None):
    return SimpleNamespace(
        id=1 if key == "owner" else 2,
        key=key,
        name=key,
        is_protected=protected,
        admin_login_allowed=admin_login,
        perms=perms or {},
    )


def test_is_staff_account_and_assert_can_reset_twofa():
    owner = SimpleNamespace(role=_make_role("owner", protected=True, admin_login=True, perms={"*": True}))
    admin = SimpleNamespace(role=_make_role("admin", admin_login=True, perms={"users": True}))
    privacy_mgr = SimpleNamespace(role=_make_role("priv", perms={"privacy": {"user": {"2fa": {"reset": True}}}}))
    regular_user = SimpleNamespace(role=_make_role("user", perms={"user": {"*": True}}))

    assert is_staff_account(owner) is True
    assert is_staff_account(admin) is True
    assert is_staff_account(privacy_mgr) is True
    assert is_staff_account(regular_user) is False

    # Обычному админу можно сбрасывать 2FA обычному пользователю
    assert_can_reset_twofa(admin, regular_user)

    # Обычный админ НЕ может сбрасывать 2FA другому админу или сотруднику
    with pytest.raises(HTTPException) as exc1:
        assert_can_reset_twofa(admin, admin)
    assert exc1.value.status_code == 403

    with pytest.raises(HTTPException) as exc2:
        assert_can_reset_twofa(admin, privacy_mgr)
    assert exc2.value.status_code == 403

    # Owner может сбрасывать 2FA кому угодно
    assert_can_reset_twofa(owner, admin)
    assert_can_reset_twofa(owner, privacy_mgr)
    assert_can_reset_twofa(owner, regular_user)


@pytest.mark.asyncio
async def test_twofa_disable_requires_valid_code_and_revokes_sessions(monkeypatch):
    acc = SimpleNamespace(id=10, totp_enabled=True, has_pass=True, pass_hash="hash")
    mngr = SimpleNamespace(s=AsyncMock())
    tokens = SimpleNamespace(revoke_all_sessions=AsyncMock())
    svc = SimpleNamespace(verify_any=MagicMock(return_value=False), disable=MagicMock())
    monkeypatch.setattr("api.v1.user.twofa._svc", lambda _req: svc)

    with pytest.raises(HTTPException) as exc:
        await twofa_disable(
            request=MagicMock(),
            body=TwoFADisable(code="000000"),
            acc=acc,
            mngr=mngr,
            tokens=tokens,
        )
    assert exc.value.status_code == 401
    svc.disable.assert_not_called()
    tokens.revoke_all_sessions.assert_not_awaited()

    svc.verify_any.return_value = True
    await twofa_disable(
        request=MagicMock(),
        body=TwoFADisable(code="123456"),
        acc=acc,
        mngr=mngr,
        tokens=tokens,
    )
    svc.disable.assert_called_once_with(acc)
    mngr.s.commit.assert_awaited_once()
    tokens.revoke_all_sessions.assert_awaited_once_with(10)


@pytest.mark.asyncio
async def test_twofa_email_reset_disabled_by_default():
    acc = SimpleNamespace(id=11, totp_enabled=True, email="u@example.com")
    mngr = SimpleNamespace(s=AsyncMock())
    settings = SimpleNamespace(get_bool=AsyncMock(return_value=False))
    vk = AsyncMock()
    sender = SimpleNamespace(configured=True)

    with pytest.raises(HTTPException) as exc:
        await twofa_email_reset_request(
            acc=acc, mngr=mngr, settings=settings, vk=vk, sender=sender
        )
    assert exc.value.status_code == 403


def test_gdpr_cooldown_remaining_sec():
    now = utc_now()
    acc_recent = SimpleNamespace(last_security_change_at=now - timedelta(hours=2))
    rem = _cooldown_remaining_sec(acc_recent, 24)
    assert 21 * 3600 < rem <= 22 * 3600

    acc_old = SimpleNamespace(last_security_change_at=now - timedelta(hours=25))
    assert _cooldown_remaining_sec(acc_old, 24) == 0

    # Отключённый кулдаун (0 часов)
    assert _cooldown_remaining_sec(acc_recent, 0) == 0
