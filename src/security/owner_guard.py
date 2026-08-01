"""Единая защита привилегированных аккаунтов и ролей.

Раньше проверки `role.key == "owner"` были размазаны по шести хендлерам
`admin/users.py` и `admin/roles.py`. Любой новый роут над `accounts` был обязан
вспомнить про владельца — из-за чего смена email владельца проходила мимо
защиты (см. AUDIT.md §1.2 SEC-C1). Здесь — единственное место, где живёт это
правило.

Признак защищённости — колонка `roles.is_protected` (по умолчанию true только
у `owner`). Через API флаг не редактируется: иначе администратор с `roles.edit`
пометил бы собственную роль защищённой.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, status

if TYPE_CHECKING:
    from models.roles import Role
    from models.user import UserModel


def is_protected_role(role: "Role | None") -> bool:
    return role is not None and bool(role.is_protected)


def _label(role: "Role | None") -> str:
    return (role.key or role.name) if role is not None else "protected"


def assert_can_modify_account(caller: "UserModel", target: "UserModel") -> None:
    """Изменять защищённый аккаунт может только носитель той же роли.

    Вызывается до любой мутации полей аккаунта — включая общий ``setattr``-цикл,
    чтобы новые поля ``UserPatch`` попадали под защиту автоматически.
    """
    if not is_protected_role(target.role):
        return
    caller_id = caller.role.id if caller.role else None
    target_id = target.role.id if target.role else None
    if caller_id != target_id:
        label = _label(target.role)
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"the {label} account can only be modified by the {label}",
        )


def assert_account_deletable(target: "UserModel") -> None:
    """Защищённый аккаунт не удаляется никем, включая его самого."""
    if is_protected_role(target.role):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"the {_label(target.role)} account cannot be deleted",
        )


def assert_role_assignable(role: "Role | None") -> None:
    """Защищённую роль нельзя выдать через API ни при каких правах."""
    if is_protected_role(role):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"the {_label(role)} role cannot be assigned"
        )


def assert_role_editable(role: "Role | None") -> None:
    if is_protected_role(role):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"the {_label(role)} role cannot be edited via API",
        )


__all__ = [
    "assert_account_deletable",
    "assert_can_modify_account",
    "assert_role_assignable",
    "assert_role_editable",
    "is_protected_role",
]
