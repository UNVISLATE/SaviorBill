"""Единая защита привилегированных аккаунтов и ролей."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, status

if TYPE_CHECKING:
    from models.roles import Role
    from models.user import UserModel


def is_protected_role(role: "Role | None") -> bool:
    return role is not None and bool(role.is_protected)


def is_staff_account(target: "UserModel") -> bool:
    """Является ли аккаунт сотрудником/администратором (имеет админские или приватные права)."""
    role = getattr(target, "role", None)
    if role is None:
        return False
    if role.is_protected or getattr(role, "admin_login_allowed", False):
        return True
    perms = role.perms if isinstance(role.perms, dict) else {}
    staff_roots = {"*", "admin", "privacy", "users", "roles", "settings", "audit", "system", "oauth", "lua"}
    return any(k in staff_roots for k in perms)


def assert_can_reset_twofa(caller: "UserModel", target: "UserModel") -> None:
    """Сбросить 2FA сотруднику/админу может только owner; админ — только обычным юзерам."""
    if is_protected_role(caller.role):
        return
    if is_staff_account(target):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "only owner can reset 2FA for admin or staff accounts",
        )


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
