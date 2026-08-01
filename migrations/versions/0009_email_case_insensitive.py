"""accounts.email — нормализация регистра и уникальность без учёта регистра

Revision ID: 0009_email_case_insensitive
Revises: 0008_lua_script_versions
Create Date: 2026-08-01 00:00:00.000000

Проверка занятости email была регистрозависимой, поэтому `User@X.com` и
`user@x.com` считались разными адресами: регистрация проходила проверку и
падала на уникальном индексе с HTTP 500, а сброс пароля мог не найти аккаунт
(см. AUDIT.md §2.1).
"""

from alembic import op


revision = '0009_email_case_insensitive'
down_revision = '0008_lua_script_versions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Приводим к нижнему регистру только там, где это не создаёт коллизию.
    op.execute(
        """
        UPDATE accounts a
        SET email = lower(a.email)
        WHERE a.email IS NOT NULL
          AND a.email <> lower(a.email)
          AND NOT EXISTS (
              SELECT 1 FROM accounts b
              WHERE b.id <> a.id AND b.email = lower(a.email)
          )
        """
    )
    # Оставшиеся дубликаты (реально два аккаунта на один адрес) чинятся
    # руками: CREATE UNIQUE INDEX упадёт с указанием конфликтного значения.
    # Склеивать или удалять аккаунты миграция не вправе.
    op.execute(
        "CREATE UNIQUE INDEX uq_accounts_email_lower "
        "ON accounts (lower(email)) WHERE email IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_accounts_email_lower")
