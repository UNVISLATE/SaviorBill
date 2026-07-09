"""promo_catalogs cleanup: drop parent_id/settings, per_user nullable, checks

Revision ID: 0013_promo_catalogs_cleanup
Revises: 0012_digikeys_encrypt
Create Date: 2026-07-09 00:00:00.000000

Аудит выявил, что каталоги промокодов (``promo_catalogs``) не образуют
осмысленную иерархию: ``parent_id`` нигде не читался в бизнес-логике, а
``ondelete=CASCADE`` на self-FK мог незаметно удалить дочерние каталоги (и
их промокоды, каскадно) при удалении родителя. Поле убрано — каталоги
промокодов остаются плоским списком.

``settings`` тоже не использовалось нигде в коде (в отличие от
``lua_scripts.settings``, который реально попадает в ``ctx.lua.settings``)
— убрано как мёртвый функционал. ``conditions`` оставлено зарезервированным
для будущей реализации условий активации.

``discount_type`` становится ``NULL``-able и осмыслен только при
``kind = discount`` — раньше поле было обязательным всегда, что позволяло
создать противоречивую запись вроде ``kind=service,
discount_type=percent``. Согласованность теперь дополнительно защищена
CHECK-констрейнтом на уровне БД (второй барьер после валидации в
приложении — см. ``PromoCatalogsMngr._validate_kind_discount`` и
``schemas.promo``).

``per_user`` становится ``NULL``-able: ``NULL`` — лимита на число разных
погашенных кодов каталога нет, число ``>= 1`` — конкретный лимит. Раньше
поле было обязательным с дефолтом ``1``, что не позволяло явно выразить
"без лимита" отдельно от "выключен" (0 который был бы логически
некорректен). CHECK запрещает 0 и отрицательные значения на уровне БД.

ВНИМАНИЕ: `downgrade()` восстанавливает колонки со значениями по
умолчанию, но данные, хранившиеся в `parent_id`/`settings` до апгрейда,
необратимо утеряны — откат не восстанавливает прежние связи/настройки.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_promo_catalogs_cleanup"
down_revision = "0012_digikeys_encrypt"
branch_labels = None
depends_on = None

_CK_KIND_DISCOUNT = "ck_promo_catalogs_kind_discount_type"
_CK_PER_USER = "ck_promo_catalogs_per_user_positive"


def upgrade() -> None:
    # parent_id: сначала FK/индекс, потом колонка.
    op.drop_constraint(
        "promo_catalogs_parent_id_fkey", "promo_catalogs", type_="foreignkey"
    )
    op.drop_index(op.f("ix_promo_catalogs_parent_id"), table_name="promo_catalogs")
    op.drop_column("promo_catalogs", "parent_id")

    # settings: мёртвое поле.
    op.drop_column("promo_catalogs", "settings")

    # discount_type: обязателен только при kind=discount.
    op.alter_column(
        "promo_catalogs",
        "discount_type",
        existing_type=sa.String(length=8),
        nullable=True,
    )

    # per_user: NULL — без лимита; убираем прежний дефолт "1".
    op.alter_column(
        "promo_catalogs",
        "per_user",
        existing_type=sa.Integer(),
        nullable=True,
        server_default=None,
    )

    op.create_check_constraint(
        _CK_KIND_DISCOUNT,
        "promo_catalogs",
        "(kind <> 'discount' AND discount_type IS NULL) "
        "OR (kind = 'discount' AND discount_type IS NOT NULL)",
    )
    op.create_check_constraint(
        _CK_PER_USER,
        "promo_catalogs",
        "per_user IS NULL OR per_user >= 1",
    )


def downgrade() -> None:
    op.drop_constraint(_CK_PER_USER, "promo_catalogs", type_="check")
    op.drop_constraint(_CK_KIND_DISCOUNT, "promo_catalogs", type_="check")

    op.execute("UPDATE promo_catalogs SET per_user = 1 WHERE per_user IS NULL")
    op.alter_column(
        "promo_catalogs",
        "per_user",
        existing_type=sa.Integer(),
        nullable=False,
        server_default="1",
    )

    op.execute(
        "UPDATE promo_catalogs SET discount_type = 'percent' "
        "WHERE discount_type IS NULL"
    )
    op.alter_column(
        "promo_catalogs",
        "discount_type",
        existing_type=sa.String(length=8),
        nullable=False,
        server_default="percent",
    )

    op.add_column(
        "promo_catalogs",
        sa.Column(
            "settings", sa.JSON(), server_default=sa.text("'{}'"), nullable=False
        ),
    )

    op.add_column(
        "promo_catalogs", sa.Column("parent_id", sa.Integer(), nullable=True)
    )
    op.create_index(
        op.f("ix_promo_catalogs_parent_id"),
        "promo_catalogs",
        ["parent_id"],
        unique=False,
    )
    op.create_foreign_key(
        "promo_catalogs_parent_id_fkey",
        "promo_catalogs",
        "promo_catalogs",
        ["parent_id"],
        ["id"],
        ondelete="CASCADE",
    )
