"""Юнит-тесты защиты от open-redirect в ``return_url`` (AUDIT.md §2.5)."""

from __future__ import annotations

import pytest

from utils.urls import is_safe_return_url

pytestmark = pytest.mark.unit

_ALLOWED = ["https://app.example.com", "http://localhost:8000"]


def test_relative_path_allowed():
    assert is_safe_return_url("/purchases/thanks", _ALLOWED) is True


def test_protocol_relative_url_rejected():
    """``//evil.com/...`` парсится браузером как абсолютный URL на evil.com,
    хотя выглядит как относительный путь — классический обход фильтра."""
    assert is_safe_return_url("//evil.com/phish", _ALLOWED) is False


def test_absolute_url_with_allowed_origin_ok():
    assert is_safe_return_url("https://app.example.com/thanks?x=1", _ALLOWED) is True


def test_absolute_url_with_foreign_origin_rejected():
    assert is_safe_return_url("https://evil.com/phish", _ALLOWED) is False


def test_same_host_different_scheme_rejected():
    """Origin — это scheme+host+port вместе, не только host."""
    assert is_safe_return_url("http://app.example.com/x", _ALLOWED) is False


def test_empty_url_rejected():
    assert is_safe_return_url("", _ALLOWED) is False


def test_javascript_scheme_rejected():
    assert is_safe_return_url("javascript:alert(1)", _ALLOWED) is False
