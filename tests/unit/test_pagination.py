"""Юнит-тесты utils/pagination — page_params и PageParams."""

from __future__ import annotations

import pytest

from utils.pagination import PageParams, page_params

pytestmark = pytest.mark.unit


def test_page_params_uses_skip_when_no_offset():
    result = page_params(limit=10, offset=None, skip=5)
    assert result == PageParams(limit=10, offset=5)


def test_page_params_prefers_offset_over_skip():
    result = page_params(limit=10, offset=20, skip=5)
    assert result == PageParams(limit=10, offset=20)


def test_page_params_offset_zero_overrides_skip():
    """offset=0 явно задан — skip должен игнорироваться."""
    result = page_params(limit=10, offset=0, skip=99)
    assert result == PageParams(limit=10, offset=0)


def test_page_params_defaults():
    result = page_params(limit=50, offset=None, skip=0)
    assert result.limit == 50
    assert result.offset == 0


def test_page_params_skip_zero():
    result = page_params(limit=25, offset=None, skip=0)
    assert result == PageParams(limit=25, offset=0)
