"""Юнит-тесты для подсистемы постоянных токенов приложений (App Tokens)."""

from __future__ import annotations

from datetime import timedelta
import pytest

from models.app_tokens import AppTokenModel, generate_app_token, hash_app_token
from security.rbac import has_perm
from utils.datetime_utils import utc_now

pytestmark = [pytest.mark.unit]


def test_generate_and_hash_app_token():
    full_token, prefix, token_hash = generate_app_token()

    assert full_token.startswith("sb_app_live_")
    assert len(full_token) > 40
    assert prefix == full_token[:16] + "..."
    assert len(token_hash) == 64
    assert hash_app_token(full_token) == token_hash


def test_app_token_perms_tree():
    token = AppTokenModel(
        name="Bot",
        token_prefix="sb_app_live_test",
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
        token_prefix="sb_app_live_any",
        token_hash="hash",
        permissions=[],
        ip_allowlist=None,
    )
    assert token_any.check_ip_allowed("1.2.3.4") is True
    assert token_any.check_ip_allowed("192.168.1.50") is True

    # С белым списком: точный IP и CIDR
    token_restricted = AppTokenModel(
        name="Bot Restricted",
        token_prefix="sb_app_live_res",
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
        token_prefix="sb_app_live_exp",
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
