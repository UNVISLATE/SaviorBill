"""Тесты Этапа E: профиль `user/me` — расширенные данные, логин по email,
частичное редактирование (со сбросом верификации), смена пароля, аватар.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from api.v1.user.me import (
    _email_confirmed_by_oauth,
    _is_media_still_used,
    _release_old_avatar,
)
from models.user import UserMngr
from schemas.auth import Account, AvatarSet, Login, MePatch, PasswordChange

pytestmark = pytest.mark.unit


class TestEmailConfirmedByOauth:
    def test_no_new_email_never_confirmed(self) -> None:
        assert _email_confirmed_by_oauth(None, ["a@b.c"]) is False
        assert _email_confirmed_by_oauth("", ["a@b.c"]) is False

    def test_matching_oauth_email_confirms(self) -> None:
        assert _email_confirmed_by_oauth("a@b.c", ["x@y.z", "a@b.c"]) is True

    def test_case_insensitive_match(self) -> None:
        assert _email_confirmed_by_oauth("A@B.C", ["a@b.c"]) is True

    def test_no_match_not_confirmed(self) -> None:
        assert _email_confirmed_by_oauth("a@b.c", ["x@y.z"]) is False

    def test_none_entries_in_oauth_emails_ignored(self) -> None:
        assert _email_confirmed_by_oauth("a@b.c", [None, "a@b.c"]) is True
        assert _email_confirmed_by_oauth("a@b.c", [None, None]) is False


class TestIsMediaStillUsed:
    @pytest.mark.asyncio
    async def test_true_when_another_account_uses_it_as_avatar(self) -> None:
        session = SimpleNamespace(scalar=AsyncMock(side_effect=[99]))
        used = await _is_media_still_used(session, 5, exclude_account_id=1)
        assert used is True
        assert session.scalar.await_count == 1  # short-circuits, no attachment lookup

    @pytest.mark.asyncio
    async def test_true_when_used_as_attachment(self) -> None:
        session = SimpleNamespace(scalar=AsyncMock(side_effect=[None, 7]))
        used = await _is_media_still_used(session, 5, exclude_account_id=1)
        assert used is True
        assert session.scalar.await_count == 2

    @pytest.mark.asyncio
    async def test_false_when_orphaned(self) -> None:
        session = SimpleNamespace(scalar=AsyncMock(side_effect=[None, None]))
        used = await _is_media_still_used(session, 5, exclude_account_id=1)
        assert used is False


class TestReleaseOldAvatar:
    def _request(self) -> SimpleNamespace:
        settings = SimpleNamespace(
            MEDIA_TASK_STREAM="media:tasks",
            MEDIA_TASK_STREAM_MAXLEN=10_000,
            BUS_SIGNING_KEY="",
        )
        return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))

    @pytest.mark.asyncio
    async def test_skips_media_not_owned_by_account(self) -> None:
        old = SimpleNamespace(id=5, owner_id=2, backend="fs", path="5.webp")
        media = SimpleNamespace(s=SimpleNamespace(scalar=AsyncMock()), delete=AsyncMock())
        vk = SimpleNamespace(xadd=AsyncMock())
        await _release_old_avatar(self._request(), vk, media, old, exclude_account_id=1)
        media.delete.assert_not_awaited()
        vk.xadd.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_when_still_referenced_elsewhere(self) -> None:
        old = SimpleNamespace(id=5, owner_id=1, backend="fs", path="5.webp")
        session = SimpleNamespace(scalar=AsyncMock(side_effect=[99]))
        media = SimpleNamespace(s=session, delete=AsyncMock())
        vk = SimpleNamespace(xadd=AsyncMock())
        await _release_old_avatar(self._request(), vk, media, old, exclude_account_id=1)
        media.delete.assert_not_awaited()
        vk.xadd.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deletes_orphaned_own_media(self) -> None:
        old = SimpleNamespace(id=5, owner_id=1, backend="fs", path="5.webp")
        session = SimpleNamespace(scalar=AsyncMock(side_effect=[None, None]))
        media = SimpleNamespace(s=session, delete=AsyncMock())
        vk = SimpleNamespace(xadd=AsyncMock())
        await _release_old_avatar(self._request(), vk, media, old, exclude_account_id=1)
        media.delete.assert_awaited_once_with(old)
        vk.xadd.assert_awaited_once()


class TestUserMngrByLoginOrEmail:
    @pytest.mark.asyncio
    async def test_prefers_login_match(self) -> None:
        mngr = UserMngr(session=None)
        found_by_login = SimpleNamespace(id=1)
        mngr.by_login = AsyncMock(return_value=found_by_login)
        mngr.by_email = AsyncMock(return_value=None)

        result = await mngr.by_login_or_email("someone")
        assert result is found_by_login
        mngr.by_login.assert_awaited_once_with("someone")
        mngr.by_email.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_falls_back_to_email(self) -> None:
        mngr = UserMngr(session=None)
        found_by_email = SimpleNamespace(id=2)
        mngr.by_login = AsyncMock(return_value=None)
        mngr.by_email = AsyncMock(return_value=found_by_email)

        result = await mngr.by_login_or_email("a@b.c")
        assert result is found_by_email
        mngr.by_email.assert_awaited_once_with("a@b.c")

    @pytest.mark.asyncio
    async def test_none_when_neither_matches(self) -> None:
        mngr = UserMngr(session=None)
        mngr.by_login = AsyncMock(return_value=None)
        mngr.by_email = AsyncMock(return_value=None)

        assert await mngr.by_login_or_email("nobody") is None


class TestLoginSchema:
    def test_accepts_email_as_login_field(self) -> None:
        body = Login(login="user@example.com", password="secret123")
        assert body.login == "user@example.com"


class TestMePatchSchema:
    def test_all_fields_optional(self) -> None:
        body = MePatch()
        assert body.model_fields_set == set()

    def test_login_only(self) -> None:
        body = MePatch(login="newlogin")
        assert body.model_dump(exclude_unset=True) == {"login": "newlogin"}

    def test_email_only(self) -> None:
        body = MePatch(email="new@example.com")
        assert body.model_dump(exclude_unset=True) == {"email": "new@example.com"}

    def test_login_too_short_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MePatch(login="ab")


class TestPasswordChangeSchema:
    def test_current_password_optional(self) -> None:
        body = PasswordChange(new_password="newpassword123")
        assert body.current_password is None

    def test_new_password_min_length_enforced(self) -> None:
        with pytest.raises(ValidationError):
            PasswordChange(new_password="short")


class TestAvatarSetSchema:
    def test_media_id_required_key_but_nullable(self) -> None:
        body = AvatarSet(media_id=None)
        assert body.media_id is None

    def test_media_id_set(self) -> None:
        body = AvatarSet(media_id=42)
        assert body.media_id == 42

    def test_missing_media_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AvatarSet()


def _account_row(**overrides) -> SimpleNamespace:
    base = dict(
        id=1,
        login="john",
        email="john@example.com",
        is_active=True,
        is_verified=True,
        role=SimpleNamespace(name="user"),
        ref_code="abc123",
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 2),
        last_login=datetime(2026, 6, 1),
        balance=Decimal("10.50"),
        bonus_balance=Decimal("2.00"),
        avatar_media_id=None,
        avatar_media=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestAccountSchema:
    def test_from_account_full_fields(self) -> None:
        row = _account_row(avatar_media_id=7, avatar_media=SimpleNamespace(token="tok7"))
        acc = Account.from_account(row, oauth_providers=["google", "yandex"])
        assert acc.balance == Decimal("10.50")
        assert acc.bonus_balance == Decimal("2.00")
        assert acc.last_login == datetime(2026, 6, 1)
        assert acc.avatar_media_id == 7
        assert acc.avatar_url == "/api/media/tok7"
        assert acc.oauth_providers == ["google", "yandex"]

    def test_from_account_no_avatar(self) -> None:
        row = _account_row()
        acc = Account.from_account(row)
        assert acc.avatar_media_id is None
        assert acc.avatar_url is None
        assert acc.oauth_providers == []
