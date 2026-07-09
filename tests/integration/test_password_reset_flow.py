"""Интеграционные тесты режимов `password.reset.method` (disabled/authenticated).

Проверяет сквозной сценарий поверх живого стека: email-роуты сброса пароля
блокируются в режимах `authenticated`/`disabled`, а смена пароля авторизованным
пользователем (`POST /me/password`) остаётся доступной в `authenticated` и
блокируется только в `disabled`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
import valkey.asyncio as valkey
from sqlalchemy import text

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_SETTING_KEY = "password.reset.method"
_CACHE_PREFIX = "settings:"


@pytest_asyncio.fixture
async def reset_method(cfg, engine) -> AsyncIterator[callable]:
    """Хелпер для установки `password.reset.method` в обход кэша Valkey.

    Пишет значение напрямую в таблицу settings и сбрасывает кэш-ключ, чтобы
    следующий запрос гарантированно перечитал БД. По завершении теста строка
    удаляется, чтобы не влиять на остальные тесты сьюта (дефолт — `code`).
    """
    vk = valkey.from_url(cfg.valkey_url, decode_responses=True)

    async def _set(value: str) -> None:
        async with engine.begin() as c:
            await c.execute(
                text(
                    "INSERT INTO settings (key,value,is_secret) VALUES "
                    "(:k,:v,false) ON CONFLICT (key) DO UPDATE SET value=:v"
                ),
                {"k": _SETTING_KEY, "v": value},
            )
        await vk.delete(_CACHE_PREFIX + _SETTING_KEY)

    try:
        yield _set
    finally:
        async with engine.begin() as c:
            await c.execute(
                text("DELETE FROM settings WHERE key=:k"), {"k": _SETTING_KEY}
            )
        await vk.delete(_CACHE_PREFIX + _SETTING_KEY)
        await vk.aclose()


async def test_email_reset_blocked_when_disabled(http, new_user, reset_method):
    await reset_method("disabled")
    login, _, _ = await new_user()
    r = await http.post(
        "/api/v1/auth/password/reset/request",
        json={"email": f"{login}@test.io"},
    )
    assert r.status_code == 404


async def test_email_reset_blocked_when_authenticated_only(
    http, new_user, reset_method
):
    await reset_method("authenticated")
    login, _, _ = await new_user()
    r = await http.post(
        "/api/v1/auth/password/reset/request",
        json={"email": f"{login}@test.io"},
    )
    assert r.status_code == 404


async def test_change_password_blocked_when_disabled(http, new_user, reset_method):
    await reset_method("disabled")
    login, pwd, tokens = await new_user()
    hdr = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = await http.post(
        "/api/v1/user/me/password",
        json={"current_password": pwd, "new_password": "newsecret123"},
        headers=hdr,
    )
    assert r.status_code == 403


async def test_change_password_allowed_when_authenticated_only(
    http, new_user, reset_method
):
    await reset_method("authenticated")
    login, pwd, tokens = await new_user()
    hdr = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = await http.post(
        "/api/v1/user/me/password",
        json={"current_password": pwd, "new_password": "newsecret123"},
        headers=hdr,
    )
    assert r.status_code == 204

    # Новый пароль действительно применился.
    r = await http.post(
        "/api/v1/auth/login", json={"login": login, "password": "newsecret123"}
    )
    assert r.status_code == 200
