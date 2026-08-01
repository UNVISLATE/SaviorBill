"""Единая защита привилегированных аккаунтов и ролей.

Раньше проверки `role.key == "owner"` были размазаны по шести хендлерам
`admin/users.py` и `admin/roles.py`. Любой новый роут над `accounts` был обязан
вспомнить про владельца — из-за чего смена email владельца проходила мимо
защиты (см. AUDIT.md §1.2 SEC-C1). Здесь — единственное место, где живёт это
правило.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, status

if TYPE_CHECKING:
    from models.roles import Role
    from models.user import UserModel

# Ключи ролей, аккаунты которых нельзя трогать чужими руками и которые нельзя
# выдать/отредактировать через API. Расширяется без правки хендлеров.
PROTECTED_ROLE_KEYS: frozenset[str] = frozenset({"owner"})


def is_protected_role(role: "Role | None") -> bool:
    return role is not None and role.key in PROTECTED_ROLE_KEYS


def assert_can_modify_account(caller: "UserModel", target: "UserModel") -> None:
    """Изменять защищённый аккаунт может только носитель той же роли.

    Вызывается до любой мутации полей аккаунта — включая общий ``setattr``-цикл,
    чтобы новые поля ``UserPatch`` попадали под защиту автоматически.
    """
    if not is_protected_role(target.role):
        return
    caller_key = caller.role.key if caller.role else None
    target_key = target.role.key if target.role else None
    if caller_key != target_key:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"the {target_key} account can only be modified by the {target_key}",
        )


def assert_account_deletable(target: "UserModel") -> None:
    """Защищённый аккаунт не удаляется никем, включая его самого."""
    if is_protected_role(target.role):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"the {target.role.key} account cannot be deleted",
        )


def assert_role_assignable(role: "Role | None") -> None:
    """Защищённую роль нельзя выдать через API ни при каких правах."""
    if is_protected_role(role):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"the {role.key} role cannot be assigned"
        )


def assert_role_editable(role: "Role | None") -> None:
    if is_protected_role(role):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"the {role.key} role cannot be edited via API"
        )


__all__ = [
    "PROTECTED_ROLE_KEYS",
    "assert_account_deletable",
    "assert_can_modify_account",
    "assert_role_assignable",
    "assert_role_editable",
    "is_protected_role",
]
