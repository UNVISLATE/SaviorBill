"""Юнит-тесты единой защиты привилегированных аккаунтов и ролей."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from security.owner_guard import (
    assert_account_deletable,
    assert_can_modify_account,
    assert_role_assignable,
    assert_role_editable,
    is_protected_role,
)

pytestmark = pytest.mark.unit


def _role(key, protected=None):
    return SimpleNamespace(
        id=hash(key) & 0xFFFF,
        key=key,
        name=key,
        is_protected=(key == "owner") if protected is None else protected,
    )


def _acc(role_key, protected=None):
    return SimpleNamespace(
        id=1, role=_role(role_key, protected) if role_key else None
    )


def test_owner_role_is_protected():
    assert is_protected_role(_role("owner")) is True
    assert is_protected_role(_role("admin")) is False
    assert is_protected_role(None) is False


def test_protection_follows_the_flag_not_the_key():
    """Флаг is_protected распространяет защиту на любую роль без правки кода."""
    custom = _role("compliance", protected=True)
    assert is_protected_role(custom) is True
    with pytest.raises(HTTPException):
        assert_role_editable(custom)


def test_admin_cannot_modify_owner_account():
    with pytest.raises(HTTPException) as e:
        assert_can_modify_account(_acc("admin"), _acc("owner"))
    assert e.value.status_code == 403


def test_owner_can_modify_owner_account():
    assert_can_modify_account(_acc("owner"), _acc("owner"))


def test_modifying_regular_account_is_unrestricted():
    assert_can_modify_account(_acc("admin"), _acc("user"))
    assert_can_modify_account(_acc(None), _acc(None))


def test_owner_account_is_never_deletable():
    with pytest.raises(HTTPException) as e:
        assert_account_deletable(_acc("owner"))
    assert e.value.status_code == 403
    assert_account_deletable(_acc("user"))


def test_owner_role_cannot_be_assigned_or_edited():
    for fn in (assert_role_assignable, assert_role_editable):
        with pytest.raises(HTTPException) as e:
            fn(_role("owner"))
        assert e.value.status_code == 403
    assert_role_assignable(_role("user"))
    assert_role_assignable(None)
    assert_role_editable(_role("manager"))
