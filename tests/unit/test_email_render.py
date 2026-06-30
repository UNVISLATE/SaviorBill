"""Юнит-тесты рендера email-шаблонов (jinja2, песочница)."""

from __future__ import annotations

import pytest
from jinja2 import UndefinedError
from jinja2.exceptions import SecurityError

from integrations.email.renderer import MailRenderer

pytestmark = pytest.mark.unit


def test_subject_renders_and_strips():
    r = MailRenderer()
    out = r.subject("  Привет, {{ user.login }}!  ", {"user": {"login": "bob"}})
    assert out == "Привет, bob!"


def test_html_body_autoescapes():
    r = MailRenderer()
    out = r.body("{{ val }}", {"val": "<b>x</b>"}, is_html=True)
    assert "&lt;b&gt;" in out
    assert "<b>" not in out


def test_text_body_no_escape():
    r = MailRenderer()
    out = r.body("{{ val }}", {"val": "<b>x</b>"}, is_html=False)
    assert out == "<b>x</b>"


def test_missing_var_raises():
    r = MailRenderer()
    with pytest.raises(UndefinedError):
        r.body("{{ missing }}", {}, is_html=False)


def test_sandbox_blocks_attribute_access():
    r = MailRenderer()
    # Доступ к dunder-атрибутам запрещён песочницей.
    with pytest.raises(SecurityError):
        r.body("{{ ().__class__ }}", {}, is_html=False)
