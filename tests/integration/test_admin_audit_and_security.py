"""Интеграционные тесты Admin API, аудита и настроек безопасности."""

from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_admin_user_ban_unban_and_audit_log(http, new_user, engine):
    """Блокировка/разблокировка пользователя админом отражается в БД и пишется в audit_logs."""
    admin_login, admin_pwd, _ = await new_user()
    async with engine.begin() as c:
        await c.execute(
            text(
                "UPDATE accounts SET role_id=(SELECT id FROM roles WHERE name='owner') "
                "WHERE login=:login"
            ),
            {"login": admin_login},
        )
    login_resp = await http.post(
        "/api/v1/auth/login", json={"login": admin_login, "password": admin_pwd}
    )
    assert login_resp.status_code == 200, login_resp.text
    admin_hdr = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    target_login, _, _ = await new_user()
    async with engine.begin() as c:
        target_id = await c.scalar(
            text("SELECT id FROM accounts WHERE login=:l"), {"l": target_login}
        )
    assert target_id is not None

    ban_resp = await http.patch(
        f"/api/v1/admin/users/{target_id}",
        json={"is_active": False},
        headers=admin_hdr,
    )
    assert ban_resp.status_code == 200, ban_resp.text
    assert ban_resp.json()["is_active"] is False

    unban_resp = await http.patch(
        f"/api/v1/admin/users/{target_id}",
        json={"is_active": True},
        headers=admin_hdr,
    )
    assert unban_resp.status_code == 200, unban_resp.text
    assert unban_resp.json()["is_active"] is True

    audit_resp = await http.get("/api/v1/admin/audit?limit=20", headers=admin_hdr)
    assert audit_resp.status_code == 200, audit_resp.text
    items = audit_resp.json()["items"]
    assert any(
        item.get("action") == "admin.user.edit" and str(item.get("target_id")) == str(target_id)
        for item in items
    )
