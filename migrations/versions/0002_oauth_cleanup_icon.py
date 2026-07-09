"""oauth_cfg: drop legacy client/endpoint fields, add icon_media_id

Revision ID: 0002_oauth_cleanup_icon
Revises: 0001_init
Create Date: 2026-07-09 00:00:00.000000

Аудит (см. OVERVIEW.md, Этап B) показал, что легаси-поля
``client_id``/``client_secret_enc``/``issuer``/``authorize_url``/
``token_url``/``userinfo_url``/``jwks_uri`` в ``oauth_cfg`` — остатки
подхода до перехода на единый action-driven Lua-скрипт провайдера (по
аналогии с платёжными провайдерами). Ни в одном месте кода (``OAuthSvc``,
``services/lua_ctx.py``, роуты) они не читаются: весь флоу идёт через
``secrets_enc`` (расшифровывается в ``ctx.provider.secrets``) и ``extra``.
Подтверждено пользователем — поля снесены целиком, без миграции данных
(секреты, если реально используются каким-то внешним Lua-скриптом
напрямую через эти колонки, нужно предварительно перенести в
``secrets_enc``/``extra`` вручную ДО применения этой миграции — см.
docstring ниже про downgrade).

Добавлено ``icon_media_id`` — иконка провайдера для UI (одно вложение,
прямой FK на ``system_media``, как ``accounts.avatar_media_id``).

ВНИМАНИЕ: `downgrade()` восстанавливает колонки пустыми (`NULL`) — прежние
значения `client_id`/`authorize_url`/... необратимо утеряны, откат не
восстанавливает данные.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_oauth_cleanup_icon"
down_revision = "0001_init"
branch_labels = None
depends_on = None

_LEGACY_STRING_COLUMNS = (
    ("client_id", 255),
    ("issuer", 255),
    ("authorize_url", 512),
    ("token_url", 512),
    ("userinfo_url", 512),
    ("jwks_uri", 512),
)


def upgrade() -> None:
    for name, _length in _LEGACY_STRING_COLUMNS:
        op.drop_column("oauth_cfg", name)
    op.drop_column("oauth_cfg", "client_secret_enc")

    op.add_column(
        "oauth_cfg", sa.Column("icon_media_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_oauth_cfg_icon_media_id",
        "oauth_cfg",
        "system_media",
        ["icon_media_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_oauth_cfg_icon_media_id", "oauth_cfg", type_="foreignkey")
    op.drop_column("oauth_cfg", "icon_media_id")

    op.add_column("oauth_cfg", sa.Column("client_secret_enc", sa.Text(), nullable=True))
    for name, length in reversed(_LEGACY_STRING_COLUMNS):
        op.add_column(
            "oauth_cfg", sa.Column(name, sa.String(length=length), nullable=True)
        )
