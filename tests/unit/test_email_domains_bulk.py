"""Tests for bulk email-domain parsing and normalization."""

import pytest

from api.v1.admin.email_domains import _normalize_domain, _parse_domains

pytestmark = pytest.mark.unit


def test_normalize_domain_canonicalizes_case_and_trailing_dot():
    assert _normalize_domain("  Mail.Example.COM. ") == "mail.example.com"


@pytest.mark.parametrize(
    "value",
    ["", "localhost", "example", "bad domain.com", "@example.com", "example.c"],
)
def test_normalize_domain_rejects_invalid_values(value):
    assert _normalize_domain(value) is None


def test_parse_domains_supports_newlines_and_csv_reason():
    assert _parse_domains("Example.COM,temporary mail\nspam.test\n") == [
        (1, "Example.COM", "temporary mail"),
        (2, "spam.test", None),
    ]
