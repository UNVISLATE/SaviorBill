"""encrypt digi_keys.value: widen column to Text

Значения ключей хранятся зашифрованными через SecBox (Fernet, префикс
``enc:``) — шифротекст длиннее исходного значения, поэтому String(512) может
не вместить длинные ключи. Шифрование выполняется на уровне приложения
(``ServiceKeysMngr.create``/``create_batch``); при необходимости
перешифровать существующие строки новым ключом ротации — см.
``utils/sec/rotate.py::reencrypt_all``.

Revision ID: 0012_digikeys_encrypt
Revises: 0011_audit_log
Create Date: 2024-01-02 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_digikeys_encrypt"
down_revision = "0011_audit_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "digi_keys",
        "value",
        existing_type=sa.String(length=512),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "digi_keys",
        "value",
        existing_type=sa.Text(),
        type_=sa.String(length=512),
        existing_nullable=False,
    )
