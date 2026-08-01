"""Break-glass: восстановление доступа владельца из консоли контейнера.

Владелец — единственный аккаунт, который нельзя починить через API: его нельзя
удалить, изменить чужими руками и нельзя выдать его роль (см.
`security/owner_guard.py`). Если пароль владельца потерян, а email уже не
принадлежит компании, единственным выходом была ручная правка БД.

Запуск (нужен доступ к хосту — это и есть подтверждение полномочий)::

    docker compose exec billing python src/ownerctl.py show
    docker compose exec billing python src/ownerctl.py reset-password --login owner
    docker compose exec billing python src/ownerctl.py promote --login alice

Каждое изменение пишется в аудит-журнал и обрывает все сессии затронутого
аккаунта.
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import AppConfig
from dependencies.db import create_db_engine, create_db_sessionmaker
from dependencies.valkey import create_valkey_client
from models.roles import Role
from models.user import UserModel
from security.sec.pwd import hash_pass
from services.audit import audit
from services.auth import TokenSvc

_GENERATED_PASSWORD_BYTES = 18


async def _owner_role(session: AsyncSession) -> Role:
    role = await session.scalar(select(Role).where(Role.key == "owner"))
    if role is None:
        raise SystemExit("owner role not found: run the app once to bootstrap roles")
    return role


async def _account(session: AsyncSession, login: str) -> UserModel:
    acc = await session.scalar(select(UserModel).where(UserModel.login == login))
    if acc is None:
        raise SystemExit(f"account {login!r} not found")
    return acc


async def _revoke_sessions(cfg: AppConfig, account_id: int) -> None:
    vk = create_valkey_client(cfg.valkey_url)
    try:
        await TokenSvc(cfg, vk).revoke_all_sessions(account_id)
    finally:
        await vk.aclose()


async def cmd_show(session: AsyncSession, _cfg: AppConfig, _args) -> None:
    role = await _owner_role(session)
    rows = await session.scalars(
        select(UserModel).where(UserModel.role_id == role.id).order_by(UserModel.id)
    )
    owners = list(rows)
    if not owners:
        print("no owner accounts exist — use 'promote' to appoint one")
        return
    for acc in owners:
        print(f"id={acc.id} login={acc.login} email={acc.email or '-'}")


async def cmd_reset_password(
    session: AsyncSession, cfg: AppConfig, args
) -> None:
    acc = await _account(session, args.login)
    role = await _owner_role(session)
    if acc.role_id != role.id:
        raise SystemExit(f"{args.login!r} is not the owner; use 'promote' instead")
    password = args.password or secrets.token_urlsafe(_GENERATED_PASSWORD_BYTES)
    acc.pass_hash = hash_pass(password)
    await audit(
        session,
        action="owner.breakglass.password_reset",
        target_type="user",
        target_id=str(acc.id),
        result="warn",
        meta={"login": acc.login, "via": "ownerctl"},
    )
    await session.commit()
    await _revoke_sessions(cfg, acc.id)
    print(f"password for {acc.login!r} has been reset")
    if not args.password:
        print(f"new password: {password}")


async def cmd_promote(session: AsyncSession, cfg: AppConfig, args) -> None:
    acc = await _account(session, args.login)
    role = await _owner_role(session)
    previous_role_id = acc.role_id
    acc.role_id = role.id
    await audit(
        session,
        action="owner.breakglass.promote",
        target_type="user",
        target_id=str(acc.id),
        result="warn",
        meta={
            "login": acc.login,
            "previous_role_id": previous_role_id,
            "via": "ownerctl",
        },
    )
    await session.commit()
    await _revoke_sessions(cfg, acc.id)
    print(f"{acc.login!r} is now the owner")


_COMMANDS = {
    "show": cmd_show,
    "reset-password": cmd_reset_password,
    "promote": cmd_promote,
}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ownerctl", description="Break-glass owner account recovery"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("show", help="list accounts holding the owner role")

    reset = sub.add_parser("reset-password", help="set a new owner password")
    reset.add_argument("--login", required=True)
    reset.add_argument(
        "--password",
        help="new password; a strong one is generated and printed if omitted",
    )
    reset.add_argument("--yes", action="store_true", required=True, help="confirm")

    promote = sub.add_parser("promote", help="grant the owner role to an account")
    promote.add_argument("--login", required=True)
    promote.add_argument("--yes", action="store_true", required=True, help="confirm")

    return parser.parse_args(argv)


async def _main(argv: list[str]) -> None:
    args = _parse_args(argv)
    cfg = AppConfig()
    engine = create_db_engine(cfg.db_url)
    try:
        sm = create_db_sessionmaker(engine)
        async with sm() as session:
            await _COMMANDS[args.command](session, cfg, args)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main(sys.argv[1:]))
