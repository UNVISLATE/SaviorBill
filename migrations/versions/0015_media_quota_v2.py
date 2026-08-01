"""media v2: content_hash (глобальный дедуп) + миграция default-прав media.upload

Revision ID: 0015_media_quota_v2
Revises: 0014_lua_versioning_v2
Create Date: 2026-08-02 02:00:00.000000

``media.upload``/``media.uploadlarge`` переименованы в ``media.upload.image``/
``media.upload.video`` (см. PLAN.md D2) — под новую схему квот (общий объём
хранимых медиа, раньше отсутствовал для media.upload.video вообще, см.
AUDIT.md §1.4 HIGH-2). Здесь — только МИГРАЦИЯ УЖЕ ЗАСЕЯННЫХ ролей: трогаем
только те роли, чьи ``perms.media`` побайтово совпадают со старым дефолтом
(не хотим затирать ручные правки администратора инсталляции).

``system_media.content_hash`` — sha256 главного варианта, для дедупа
физических файлов между владельцами (хардлинк на fs, см. mediaworker
utils/worker.py::_convert + utils/storage.py::link_or_copy — ссылка ФС сама
делает reference counting, отдельного счётчика в БД не нужно).
"""

from alembic import op
import sqlalchemy as sa


revision = '0015_media_quota_v2'
down_revision = '0014_lua_versioning_v2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_media",
        sa.Column("content_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_system_media_content_hash", "system_media", ["content_hash"]
    )

    conn = op.get_bind()
    import json

    roles = conn.execute(
        sa.text("SELECT id, key, perms FROM roles WHERE key IN ('user', 'manager', 'guest')")
    ).fetchall()
    for row in roles:
        perms = dict(row.perms or {})
        media = perms.get("media")
        if row.key in ("user", "manager") and media == {"upload": True}:
            perms["media"] = {"upload": {"image": True}}
            conn.execute(
                sa.text("UPDATE roles SET perms = :perms WHERE id = :id"),
                {"perms": json.dumps(perms), "id": row.id},
            )
        elif row.key == "guest" and media == {"upload": True}:
            perms.pop("media", None)
            conn.execute(
                sa.text("UPDATE roles SET perms = :perms WHERE id = :id"),
                {"perms": json.dumps(perms), "id": row.id},
            )


def downgrade() -> None:
    op.drop_index("ix_system_media_content_hash", table_name="system_media")
    op.drop_column("system_media", "content_hash")
