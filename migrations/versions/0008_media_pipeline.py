"""media pipeline: token/status, service_attachments, avatar, drop services.image

Revision ID: 0008_media_pipeline
Revises: 0007_lua_settings
Create Date: 2026-07-01 20:00:00.000000

Рефакторинг медиа: mediaworker обрабатывает файлы, billing хранит метаданные.
- system_media: публичный ``token`` (= file_id = task_token) и ``status`` конверсии;
- новая таблица ``service_attachments`` (медиа товара: media_id + тег + позиция);
- ``accounts.avatar_media_id`` (аватар пользователя);
- удаление одиночного ``services.image`` (заменяется вложениями).
"""

import uuid

from alembic import op
import sqlalchemy as sa

revision = "0008_media_pipeline"
down_revision = "0007_lua_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # system_media.token — сначала nullable, затем backfill uuid и NOT NULL + unique.
    op.add_column(
        "system_media", sa.Column("token", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "system_media",
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="ready",
            nullable=False,
        ),
    )

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id FROM system_media")).fetchall()
    for (mid,) in rows:
        bind.execute(
            sa.text("UPDATE system_media SET token = :t WHERE id = :i"),
            {"t": uuid.uuid4().hex, "i": mid},
        )

    op.alter_column("system_media", "token", nullable=False)
    op.create_index(
        op.f("ix_system_media_token"), "system_media", ["token"], unique=True
    )

    op.create_table(
        "service_attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("media_id", sa.Integer(), nullable=False),
        sa.Column("tag", sa.String(length=16), nullable=True),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["media_id"], ["system_media.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_service_attachments_service_id"),
        "service_attachments",
        ["service_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_service_attachments_media_id"),
        "service_attachments",
        ["media_id"],
        unique=False,
    )

    op.add_column("accounts", sa.Column("avatar_media_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_accounts_avatar_media_id_system_media"),
        "accounts",
        "system_media",
        ["avatar_media_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_column("services", "image")


def downgrade() -> None:
    op.add_column("services", sa.Column("image", sa.String(length=512), nullable=True))

    op.drop_constraint(
        op.f("fk_accounts_avatar_media_id_system_media"),
        "accounts",
        type_="foreignkey",
    )
    op.drop_column("accounts", "avatar_media_id")

    op.drop_index(
        op.f("ix_service_attachments_media_id"), table_name="service_attachments"
    )
    op.drop_index(
        op.f("ix_service_attachments_service_id"), table_name="service_attachments"
    )
    op.drop_table("service_attachments")

    op.drop_index(op.f("ix_system_media_token"), table_name="system_media")
    op.drop_column("system_media", "status")
    op.drop_column("system_media", "token")
