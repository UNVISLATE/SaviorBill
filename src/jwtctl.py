"""Ротация ключевой пары подписи JWT (RS256) без мгновенного logout.

Новый ключ становится текущим (подписывает новые access/refresh-токены),
старый остаётся в key ring только для верификации ещё какое-то время — так
уже выданные токены не становятся мгновенно невалидными (см. AUDIT.md §1.5).
Toкены, подписанные ключом до ПРЕДЫДУЩЕГО (два шага назад), перестают
проходить верификацию сразу после следующей ротации — если нужен более
длинный grace-период, ротацию не запускать чаще, чем раз в
``REFRESH_TOKEN_TTL``.

Запуск (нужен доступ к хосту/контейнеру billing)::

    docker compose exec billing python src/jwtctl.py rotate --yes
    docker compose exec billing python src/jwtctl.py show
"""

from __future__ import annotations

import argparse
import sys

from core.config import AppConfig
from security.sec.secrets.resolve import resolve_secrets, rotate_jwt_keypair


def cmd_show(cfg: AppConfig, _args) -> None:
    print(f"current kid: {cfg.JWT_KID}")
    if cfg.JWT_KID_PREV:
        print(f"previous kid (grace period): {cfg.JWT_KID_PREV}")
    else:
        print("no previous kid (never rotated, or grace period ended)")


def cmd_rotate(cfg: AppConfig, _args) -> None:
    old_kid = cfg.JWT_KID
    new_kid = rotate_jwt_keypair(cfg)
    print(f"rotated: {old_kid!r} -> {new_kid!r}")
    print(
        "the previous key remains valid for verification until the next "
        "rotation — restart mediaworker is NOT required, it re-reads the key "
        "ring files on every request"
    )


_COMMANDS = {"show": cmd_show, "rotate": cmd_rotate}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="jwtctl", description="Rotate the JWT signing keypair (RS256)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show", help="print the current/previous kid")
    rotate = sub.add_parser("rotate", help="generate a new signing key")
    rotate.add_argument("--yes", action="store_true", required=True, help="confirm")
    return parser.parse_args(argv)


def main(argv: list[str]) -> None:
    args = _parse_args(argv)
    cfg = AppConfig()
    resolve_secrets(cfg)
    _COMMANDS[args.command](cfg, args)


if __name__ == "__main__":
    main(sys.argv[1:])
