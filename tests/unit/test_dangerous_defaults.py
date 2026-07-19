"""Юнит-тесты fail-fast проверки опасных ENV-дефолтов (AUDIT.md H3)."""

from __future__ import annotations

import pytest

from bootstrap.safety import InsecureDefaultsError, check_dangerous_defaults
from core.config import AppConfig

pytestmark = pytest.mark.unit


def _cfg(**overrides) -> AppConfig:
    defaults = dict(
        DEBUG=False,
        TRUSTED_PROXIES="",
        DB_PASS="s3cr3t-random-generated",
        OWNER_LOGIN="root_admin_x1",
        OWNER_PASS="a-real-random-password",
        BUS_SIGNING_KEY="a-real-random-bus-signing-key",
    )
    defaults.update(overrides)
    return AppConfig(**defaults)


def test_debug_mode_skips_check():
    """В DEBUG=true плейсхолдеры разрешены (локальная разработка)."""
    cfg = _cfg(DEBUG=True, DB_PASS="change-me", TRUSTED_PROXIES="*")
    check_dangerous_defaults(cfg)  # не должно бросать


def test_safe_config_passes():
    check_dangerous_defaults(_cfg())  # не должно бросать


def test_trusted_proxies_wildcard_rejected():
    with pytest.raises(InsecureDefaultsError, match="TRUSTED_PROXIES"):
        check_dangerous_defaults(_cfg(TRUSTED_PROXIES="*"))


@pytest.mark.parametrize("bad_pass", ["change-me", "changeme", "password", ""])
def test_placeholder_db_pass_rejected(bad_pass):
    with pytest.raises(InsecureDefaultsError, match="DB_PASS"):
        check_dangerous_defaults(_cfg(DB_PASS=bad_pass))


def test_placeholder_owner_creds_rejected():
    with pytest.raises(InsecureDefaultsError, match="OWNER_LOGIN"):
        check_dangerous_defaults(_cfg(OWNER_LOGIN="owner", OWNER_PASS="owner"))


def test_owner_login_alone_is_not_enough_to_reject():
    """Только логин совпал с плейсхолдером, но пароль — реальный: не блокируем."""
    check_dangerous_defaults(_cfg(OWNER_LOGIN="admin", OWNER_PASS="a-real-random-password"))


def test_cors_wildcard_rejected_at_config_level():
    """AUDIT.md L3 — CORS_ORIGINS=* невалиден вместе с allow_credentials=True."""
    with pytest.raises(Exception, match="CORS_ORIGINS"):
        AppConfig(CORS_ORIGINS="*")


def test_empty_bus_signing_key_rejected():
    """AUDIT.md H1 — без общего секрета шина lua/media не защищена от подделки."""
    with pytest.raises(InsecureDefaultsError, match="BUS_SIGNING_KEY"):
        check_dangerous_defaults(_cfg(BUS_SIGNING_KEY=""))
