"""Юнит-тесты utils/pagination — page_params и PageParams."""

from __future__ import annotations

import pytest

from utils.pagination import PageParams, page_params

pytestmark = pytest.mark.unit


def test_page_params_uses_given_offset():
    result = page_params(limit=10, offset=5)
    assert result == PageParams(limit=10, offset=5)


def test_page_params_defaults():
    result = page_params(limit=50, offset=0)
    assert result.limit == 50
    assert result.offset == 0
