import pytest
from pydantic import ValidationError

from schemas.user import UserCreateAdmin


def test_user_create_admin_with_avatar():
    # Valid login, password, and avatar_media_id
    data = UserCreateAdmin(
        login="test_admin_user",
        password="supersecretpassword123",
        email="user@test.org",
        role_id=2,
        avatar_media_id=42,
    )
    assert data.login == "test_admin_user"
    assert data.avatar_media_id == 42


def test_user_create_admin_without_avatar():
    data = UserCreateAdmin(
        login="cyrillic_пользователь",
        password="supersecretpassword123",
    )
    assert data.login == "cyrillic_пользователь"
    assert data.avatar_media_id is None
