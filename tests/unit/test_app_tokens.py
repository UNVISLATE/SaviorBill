"""Юнит-тесты для подсистемы постоянных токенов приложений (App Tokens)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException

from api.v1.admin.app_tokens import _can_manage_any
from models.app_tokens import AppTokenModel, generate_app_token, hash_app_token
from models.roles import Role
from models.user import UserModel
from security.rbac import has_perm
from utils.datetime_utils import utc_now

pytestmark = [pytest.mark.unit]


def test_generate_and_hash_app_token():
    full_token, prefix, token_hash = generate_app_token()

    assert full_token.startswith("sbapp_live_")
    assert len(full_token) > 40
    assert prefix == full_token[:16]
    assert "..." not in prefix
    assert prefix.startswith("sbapp_live_") and prefix.endswith("_")
    tag = prefix[len("sbapp_live_"):-1]
    assert len(tag) == 4
    assert tag == tag.lower()
    assert len(token_hash) == 64
    assert hash_app_token(full_token) == token_hash


def test_app_token_perms_tree():
    token = AppTokenModel(
        name="Bot",
        token_prefix="sbapp_live_test_",
        token_hash="hash",
        permissions=["orders.read", "services.keys.read", "apptokens.*"],
    )

    tree = token.perms_tree

    assert has_perm(tree, "orders.read") is True
    assert has_perm(tree, "services.keys.read") is True
    assert has_perm(tree, "apptokens.read") is True
    assert has_perm(tree, "apptokens.create") is True
    assert has_perm(tree, "apptokens.revoke") is True

    # Не выданные права:
    assert has_perm(tree, "users.delete") is False
    assert has_perm(tree, "settings.edit") is False
    assert has_perm(tree, "orders.create") is False


def test_app_token_ip_allowlist():
    # Без ограничений:
    token_any = AppTokenModel(
        name="Bot Any",
        token_prefix="sbapp_live_any_",
        token_hash="hash",
        permissions=[],
        ip_allowlist=None,
    )
    assert token_any.check_ip_allowed("1.2.3.4") is True
    assert token_any.check_ip_allowed("192.168.1.50") is True

    # С белым списком: точный IP и CIDR
    token_restricted = AppTokenModel(
        name="Bot Restricted",
        token_prefix="sbapp_live_res_",
        token_hash="hash",
        permissions=[],
        ip_allowlist=["10.0.0.1", "192.168.1.0/24"],
    )

    assert token_restricted.check_ip_allowed("10.0.0.1") is True
    assert token_restricted.check_ip_allowed("10.0.0.2") is False

    assert token_restricted.check_ip_allowed("192.168.1.15") is True
    assert token_restricted.check_ip_allowed("192.168.1.254") is True
    assert token_restricted.check_ip_allowed("192.168.2.1") is False

    assert token_restricted.check_ip_allowed("invalid-ip") is False


def test_app_token_expiration_and_revocation():
    token = AppTokenModel(
        name="Bot Exp",
        token_prefix="sbapp_live_exp_",
        token_hash="hash",
        permissions=[],
        is_revoked=False,
        expires_at=utc_now() + timedelta(days=1),
    )

    assert token.is_revoked is False
    assert token.expires_at > utc_now()

    # Истекший токен:
    token.expires_at = utc_now() - timedelta(minutes=1)
    assert token.expires_at < utc_now()

    # Отозванный токен:
    token.is_revoked = True
    assert token.is_revoked is True


def test_can_manage_any_tokens():
    mock_req = MagicMock()
    mock_req.state.app_token = None

    # 1. Owner can always manage any
    owner_user = UserModel(id=1, login="owner", role=Role(key="owner", perms={}))
    assert _can_manage_any(owner_user, mock_req) is True

    # 2. Manager without apptokens.manage_any cannot
    mgr_user = UserModel(id=2, login="mgr", role=Role(key="mgr", perms={"apptokens": {"read": True}}))
    assert _can_manage_any(mgr_user, mock_req) is False

    # 3. User with apptokens.manage_any can
    admin_user = UserModel(
        id=3,
        login="admin",
        role=Role(key="admin", perms={"apptokens": {"manage_any": True}}),
    )
    assert _can_manage_any(admin_user, mock_req) is True

    # 4. App Token caller with apptokens.manage_any
    app_tok = AppTokenModel(token_prefix="sbapp_live_tok_", permissions=["apptokens.manage_any"])
    mock_req.state.app_token = app_tok
    assert _can_manage_any(mgr_user, mock_req) is True
