"""Юнит-тесты сброса пароля по email: код и токен-режим (`dependencies/password.py`)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from dependencies.password import (
    METHOD_AUTHENTICATED,
    METHOD_CODE,
    METHOD_DISABLED,
    METHOD_TOKEN,
    ResetSvc,
    resolve_reset_method,
)

pytestmark = pytest.mark.unit


class _FakeValkey:
    """Мини in-memory Valkey: GET/SET/DELETE/INCR без реального TTL."""

    def __init__(self) -> None:
        self._vals: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._vals[key] = value

    async def get(self, key: str) -> str | None:
        return self._vals.get(key)

    async def delete(self, key: str) -> None:
        self._vals.pop(key, None)

    async def incr(self, key: str) -> int:
        current = int(self._vals.get(key, 0)) + 1
        self._vals[key] = str(current)
        return current


class _FakeSettings:
    def __init__(self, method: str | None = None, ttl: int = 900):
        self.method = method
        self.ttl = ttl

    async def get(self, key: str, default: str | None = None) -> str | None:
        if key == "password.reset.method":
            return self.method if self.method is not None else default
        return default

    async def get_int(self, key: str, default: int | None = None) -> int | None:
        if key == "mail.code_ttl":
            return self.ttl
        return default


class _FakeSender:
    def __init__(self, configured: bool = True, sent: bool = True):
        self._configured = configured
        self._sent = sent
        self.send_template = AsyncMock(return_value=sent)
        self.mail = SimpleNamespace(send=AsyncMock())

    @property
    def configured(self) -> bool:
        return self._configured


def _acc(id_=1, login="alice", email="alice@example.com", active=True):
    return SimpleNamespace(id=id_, login=login, email=email, is_active=active)


def _svc(vk, settings, sender, mngr_acc=None):
    session = SimpleNamespace(flush=AsyncMock())
    svc = ResetSvc(session=session, vk=vk, settings=settings, sender=sender, default_ttl=900)
    patcher = patch(
        "dependencies.password.UserMngr",
        return_value=SimpleNamespace(by_email=AsyncMock(return_value=mngr_acc)),
    )
    return svc, patcher


class TestRequestCodeMode:
    @pytest.mark.asyncio
    async def test_stores_code_and_sends_template(self) -> None:
        vk = _FakeValkey()
        sender = _FakeSender()
        acc = _acc()
        svc, patcher = _svc(vk, _FakeSettings(method=METHOD_CODE), sender, acc)
        with patcher:
            await svc.request("alice@example.com")

        stored = vk._vals["reset:pwd:alice@example.com"]
        assert stored.isdigit() and len(stored) == 6
        sender.send_template.assert_awaited_once()
        ctx = sender.send_template.await_args.args[2]
        assert ctx["code"] == stored
        assert ctx["token"] is None
        # Код-режим не создаёт обратный индекс токена.
        assert not any(k.startswith("reset:pwd:tok:") for k in vk._vals)

    @pytest.mark.asyncio
    async def test_defaults_to_code_when_setting_unset(self) -> None:
        vk = _FakeValkey()
        sender = _FakeSender()
        acc = _acc()
        svc, patcher = _svc(vk, _FakeSettings(method=None), sender, acc)
        with patcher:
            await svc.request("alice@example.com")
        assert vk._vals["reset:pwd:alice@example.com"].isdigit()

    @pytest.mark.asyncio
    async def test_silently_ignores_unknown_account(self) -> None:
        vk = _FakeValkey()
        sender = _FakeSender()
        svc, patcher = _svc(vk, _FakeSettings(method=METHOD_CODE), sender, None)
        with patcher:
            await svc.request("nobody@example.com")
        assert vk._vals == {}
        sender.send_template.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_raises_when_sender_not_configured(self) -> None:
        vk = _FakeValkey()
        sender = _FakeSender(configured=False)
        svc, patcher = _svc(vk, _FakeSettings(method=METHOD_CODE), sender, _acc())
        with patcher, pytest.raises(HTTPException) as exc:
            await svc.request("alice@example.com")
        assert exc.value.status_code == 404


class TestRequestTokenMode:
    @pytest.mark.asyncio
    async def test_stores_token_and_reverse_index(self) -> None:
        vk = _FakeValkey()
        sender = _FakeSender()
        acc = _acc()
        svc, patcher = _svc(vk, _FakeSettings(method=METHOD_TOKEN), sender, acc)
        with patcher:
            await svc.request("alice@example.com")

        stored = vk._vals["reset:pwd:alice@example.com"]
        assert len(stored) > 20  # url-safe token, не 6-значный код
        assert vk._vals["reset:pwd:tok:" + stored] == "alice@example.com"
        ctx = sender.send_template.await_args.args[2]
        assert ctx["token"] == stored
        assert ctx["code"] is None


class TestConfirm:
    @pytest.mark.asyncio
    async def test_confirm_with_email_and_code(self) -> None:
        vk = _FakeValkey()
        await vk.set("reset:pwd:alice@example.com", "123456")
        acc = _acc()
        svc, patcher = _svc(vk, _FakeSettings(), _FakeSender(), acc)
        with patcher:
            result = await svc.confirm("123456", "NewPass123", email="alice@example.com")
        assert result is acc
        assert "reset:pwd:alice@example.com" not in vk._vals

    @pytest.mark.asyncio
    async def test_confirm_with_token_no_email(self) -> None:
        vk = _FakeValkey()
        token = "sometoken1234567890"
        await vk.set("reset:pwd:alice@example.com", token)
        await vk.set("reset:pwd:tok:" + token, "alice@example.com")
        acc = _acc()
        svc, patcher = _svc(vk, _FakeSettings(), _FakeSender(), acc)
        with patcher:
            result = await svc.confirm(token, "NewPass123")
        assert result is acc
        assert "reset:pwd:tok:" + token not in vk._vals

    @pytest.mark.asyncio
    async def test_confirm_unknown_token_without_email_raises(self) -> None:
        vk = _FakeValkey()
        svc, patcher = _svc(vk, _FakeSettings(), _FakeSender(), None)
        with patcher, pytest.raises(HTTPException) as exc:
            await svc.confirm("unknown-token", "NewPass123")
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_confirm_expired_or_not_requested(self) -> None:
        vk = _FakeValkey()
        svc, patcher = _svc(vk, _FakeSettings(), _FakeSender(), _acc())
        with patcher, pytest.raises(HTTPException) as exc:
            await svc.confirm("123456", "NewPass123", email="alice@example.com")
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_confirm_wrong_code_increments_fail_counter(self) -> None:
        vk = _FakeValkey()
        await vk.set("reset:pwd:alice@example.com", "123456")
        svc, patcher = _svc(vk, _FakeSettings(), _FakeSender(), _acc())
        with patcher, pytest.raises(HTTPException) as exc:
            await svc.confirm("000000", "NewPass123", email="alice@example.com")
        assert exc.value.status_code == 400
        assert vk._vals["reset:pwd:fail:alice@example.com"] == "1"


class TestResolveResetMethod:
    @pytest.mark.asyncio
    async def test_unknown_value_defaults_to_code(self) -> None:
        settings = _FakeSettings(method="garbage")
        assert await resolve_reset_method(settings) == METHOD_CODE

    @pytest.mark.asyncio
    async def test_unset_defaults_to_code(self) -> None:
        settings = _FakeSettings(method=None)
        assert await resolve_reset_method(settings) == METHOD_CODE

    @pytest.mark.asyncio
    async def test_known_values_pass_through(self) -> None:
        for value in (METHOD_CODE, METHOD_TOKEN, METHOD_AUTHENTICATED, METHOD_DISABLED):
            assert await resolve_reset_method(_FakeSettings(method=value)) == value


class TestDisabledAndAuthenticatedModes:
    @pytest.mark.asyncio
    async def test_request_raises_404_when_disabled(self) -> None:
        vk = _FakeValkey()
        sender = _FakeSender()
        svc, patcher = _svc(vk, _FakeSettings(method=METHOD_DISABLED), sender, _acc())
        with patcher, pytest.raises(HTTPException) as exc:
            await svc.request("alice@example.com")
        assert exc.value.status_code == 404
        sender.send_template.assert_not_awaited()
        assert vk._vals == {}

    @pytest.mark.asyncio
    async def test_request_raises_404_when_authenticated_only(self) -> None:
        vk = _FakeValkey()
        sender = _FakeSender()
        svc, patcher = _svc(
            vk, _FakeSettings(method=METHOD_AUTHENTICATED), sender, _acc()
        )
        with patcher, pytest.raises(HTTPException) as exc:
            await svc.request("alice@example.com")
        assert exc.value.status_code == 404
        sender.send_template.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_confirm_raises_404_when_disabled(self) -> None:
        vk = _FakeValkey()
        await vk.set("reset:pwd:alice@example.com", "123456")
        svc, patcher = _svc(vk, _FakeSettings(method=METHOD_DISABLED), _FakeSender(), _acc())
        with patcher, pytest.raises(HTTPException) as exc:
            await svc.confirm("123456", "NewPass123", email="alice@example.com")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_confirm_raises_404_when_authenticated_only(self) -> None:
        vk = _FakeValkey()
        svc, patcher = _svc(
            vk, _FakeSettings(method=METHOD_AUTHENTICATED), _FakeSender(), _acc()
        )
        with patcher, pytest.raises(HTTPException) as exc:
            await svc.confirm("123456", "NewPass123", email="alice@example.com")
        assert exc.value.status_code == 404


class TestChangePasswordBlockedWhenDisabled:
    @pytest.mark.asyncio
    async def test_change_password_route_blocks_when_disabled(self) -> None:
        from api.v1.user.me import change_password
        from schemas.auth import PasswordChange

        settings = _FakeSettings(method=METHOD_DISABLED)
        acc = SimpleNamespace(has_pass=True, pass_hash="x")
        mngr = SimpleNamespace(s=SimpleNamespace(commit=AsyncMock()))
        body = PasswordChange(current_password="old12345", new_password="new12345")
        with pytest.raises(HTTPException) as exc:
            await change_password(body, acc=acc, mngr=mngr, settings=settings)
        assert exc.value.status_code == 403
        mngr.s.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_change_password_route_allows_when_authenticated_mode(self) -> None:
        from api.v1.user.me import change_password
        from schemas.auth import PasswordChange
        from security.sec.pwd import hash_pass

        settings = _FakeSettings(method=METHOD_AUTHENTICATED)
        acc = SimpleNamespace(has_pass=True, pass_hash=hash_pass("old12345"))
        mngr = SimpleNamespace(s=SimpleNamespace(commit=AsyncMock()))
        body = PasswordChange(current_password="old12345", new_password="new12345")
        await change_password(body, acc=acc, mngr=mngr, settings=settings)
        mngr.s.commit.assert_awaited_once()
        assert acc.pass_hash != hash_pass("old12345")  # updated to new hash
