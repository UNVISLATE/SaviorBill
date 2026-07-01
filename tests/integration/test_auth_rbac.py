"""Интеграционные тесты аутентификации и RBAC (против живого стека)."""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_health(http):
    r = await http.get("/health")
    assert r.status_code == 200


async def test_register_login_me_refresh_logout(http, new_user):
    login, pwd, tokens = await new_user()
    assert "access_token" in tokens and "refresh_token" in tokens

    # login
    r = await http.post("/api/v1/auth/login", json={"login": login, "password": pwd})
    assert r.status_code == 200
    access = r.json()["access_token"]
    refresh = r.json()["refresh_token"]

    # me
    r = await http.get("/api/v1/user/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    assert r.json()["login"] == login

    # refresh
    r = await http.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    assert "access_token" in r.json()

    # logout (отзыв refresh-токена — нужен сам refresh в теле)
    r = await http.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code in (200, 204)


async def test_duplicate_register_conflict(http, new_user):
    login, pwd, _ = await new_user()
    r = await http.post(
        "/api/v1/auth/register",
        json={"login": login, "email": "x@test.io", "password": pwd},
    )
    assert r.status_code == 409


async def test_me_requires_auth(http):
    r = await http.get("/api/v1/user/me")
    assert r.status_code in (401, 403)


async def test_wrong_password_rejected(http, new_user):
    login, _, _ = await new_user()
    r = await http.post("/api/v1/auth/login", json={"login": login, "password": "nope"})
    assert r.status_code == 401


async def test_admin_route_forbidden_for_user(http, new_user):
    _, _, tokens = await new_user()
    r = await http.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 403


async def test_admin_route_allowed_after_role_grant(http, new_user, seed):
    login, pwd, _ = await new_user()
    await seed.make_admin(login)
    # перелогиниваемся, чтобы получить токен уже с админ-ролью
    r = await http.post("/api/v1/auth/login", json={"login": login, "password": pwd})
    access = r.json()["access_token"]

    r = await http.get(
        "/api/v1/admin/users", headers={"Authorization": f"Bearer {access}"}
    )
    assert r.status_code == 200
    assert isinstance(r.json()["items"], list)

    # каталог прав доступен админу
    r = await http.get(
        "/api/v1/admin/perms", headers={"Authorization": f"Bearer {access}"}
    )
    assert r.status_code == 200
    assert "flat" in r.json() and "tree" in r.json()
