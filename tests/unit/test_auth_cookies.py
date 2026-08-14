"""Юнит-тесты валидации DOMAIN/MEDIA_DOMAIN и auth-cookie (Фаза 5, п.1)."""

from __future__ import annotations

import pytest

from core.config import AppConfig
from security.sec.cookies import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    clear_auth_cookies,
    set_auth_cookies,
)

pytestmark = pytest.mark.unit


def test_same_root_domain_ok():
    cfg = AppConfig(DOMAIN="admin.example.com", MEDIA_DOMAIN="media.example.com")
    assert cfg.cookie_domain == "example.com"


def test_different_root_domain_rejected():
    with pytest.raises(Exception, match="DOMAIN"):
        AppConfig(DOMAIN="example.com", MEDIA_DOMAIN="other.org")


def test_domain_with_port_ignored_for_comparison():
    cfg = AppConfig(DOMAIN="example.com:8000", MEDIA_DOMAIN="media.example.com:8001")
    assert cfg.cookie_domain == "example.com"


def test_localhost_domains_are_same_root():
    cfg = AppConfig(DOMAIN="localhost:8000", MEDIA_DOMAIN="localhost:8001")
    assert cfg.cookie_domain == "localhost"


def test_only_one_domain_set_is_not_a_conflict():
    cfg = AppConfig(DOMAIN="example.com", MEDIA_DOMAIN=None)
    assert cfg.cookie_domain == "example.com"


def test_no_domains_set_gives_no_cookie_domain():
    cfg = AppConfig(DOMAIN=None, MEDIA_DOMAIN=None)
    assert cfg.cookie_domain is None


class _FakeResponse:
    """Достаточно ``Response``-подобного для проверки set_cookie/delete_cookie."""

    def __init__(self) -> None:
        self.set_calls: list[dict] = []
        self.delete_calls: list[dict] = []

    def set_cookie(self, key, value, **kwargs):
        self.set_calls.append({"key": key, "value": value, **kwargs})

    def delete_cookie(self, key, **kwargs):
        self.delete_calls.append({"key": key, **kwargs})


def test_set_auth_cookies_sets_both_httponly():
    cfg = AppConfig(DOMAIN="example.com", DEBUG=False)
    resp = _FakeResponse()
    set_auth_cookies(resp, cfg, access_token="a", refresh_token="r")

    assert len(resp.set_calls) == 2
    access, refresh = resp.set_calls
    assert access["key"] == ACCESS_COOKIE
    assert access["value"] == "a"
    assert access["httponly"] is True
    assert access["secure"] is True
    assert access["samesite"] == "strict"
    assert access["path"] == "/"

    assert refresh["key"] == REFRESH_COOKIE
    assert refresh["value"] == "r"
    assert refresh["httponly"] is True
    assert refresh["path"] == "/api/v1/auth"


def test_set_auth_cookies_not_secure_in_debug():
    cfg = AppConfig(DOMAIN="example.com", DEBUG=True)
    resp = _FakeResponse()
    set_auth_cookies(resp, cfg, access_token="a", refresh_token="r")
    assert all(call["secure"] is False for call in resp.set_calls)


def test_clear_auth_cookies_deletes_both():
    cfg = AppConfig(DOMAIN="example.com")
    resp = _FakeResponse()
    clear_auth_cookies(resp, cfg)
    assert {c["key"] for c in resp.delete_calls} == {ACCESS_COOKIE, REFRESH_COOKIE}
