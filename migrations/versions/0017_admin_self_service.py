"""roles: admin/manager получают полный доступ к своим (self-service) данным

Revision ID: 0017_admin_self_service
Revises: 0016_media_expires_at
Create Date: 2026-08-02 05:00:00.000000

Баг: у ролей ``admin``/``manager`` не было ключа ``user`` в perms вообще —
все self-service роуты (``GET/PUT /me``, ``/me/media``, ``/me/services``,
``/me/purchases``, ``/me/oauth``, 2FA) требуют ``user.profile.read`` /
``user.*``, поэтому свежесозданный админ не мог даже посмотреть свой
собственный профиль сразу после логина в админку (см. bootstrap/init/role.py).

Здесь только МИГРАЦИЯ УЖЕ ЗАСЕЯННЫХ ролей: трогаем только те роли, чьи perms
побайтово совпадают со старым дефолтом (не хотим затирать ручные правки
администратора инсталляции — тот же принцип, что и в 0015_media_quota_v2).
"""

import json

from alembic import op
import sqlalchemy as sa


revision = '0017_admin_self_service'
down_revision = '0016_media_expires_at'
branch_labels = None
depends_on = None


_OLD_ADMIN_PERMS = {
    "users": True,
    "roles": True,
    "services": True,
    "catalogs": True,
    "orders": True,
    "purchases": True,
    "oauth": True,
    "lua": True,
    "email": True,
    "triggers": True,
    "media": True,
    "promo": True,
    "audit": True,
    "settings": True,
    "analytics": {"basic": {"read": True}},
    "system": {
        "tasks": {"read": True},
        "jobs": {"read": True},
        "stats": {"read": True, "instance": {"read": True}},
    },
    "admin": {"media": {"upload": True, "manage_any": True}},
}

_OLD_MANAGER_PERMS = {
    "services": True,
    "catalogs": True,
    "orders": True,
    "purchases": True,
    "promo": True,
    "triggers": {"read": True},
    "media": {"upload": {"image": True}},
}


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, key, perms FROM roles WHERE key IN ('admin', 'manager')")
    ).fetchall()
    for row in rows:
        perms = dict(row.perms or {})
        old = _OLD_ADMIN_PERMS if row.key == "admin" else _OLD_MANAGER_PERMS
        if perms == old:
            perms["user"] = {"*": True}
            conn.execute(
                sa.text("UPDATE roles SET perms = :perms WHERE id = :id"),
                {"perms": json.dumps(perms), "id": row.id},
            )


def downgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, key, perms FROM roles WHERE key IN ('admin', 'manager')")
    ).fetchall()
    for row in rows:
        perms = dict(row.perms or {})
        expected = dict(_OLD_ADMIN_PERMS if row.key == "admin" else _OLD_MANAGER_PERMS)
        expected["user"] = {"*": True}
        if perms == expected:
            perms.pop("user", None)
            conn.execute(
                sa.text("UPDATE roles SET perms = :perms WHERE id = :id"),
                {"perms": json.dumps(perms), "id": row.id},
            )
