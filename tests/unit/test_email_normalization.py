"""Нормализация email и регистронезависимый поиск аккаунта (AUDIT.md §2.1)."""

from __future__ import annotations

import pytest

from schemas.auth import MePatch, Reg
from schemas.types import normalize_email
from schemas.user import UserCreateAdmin, UserPatch

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("User@GMAIL.com", "user@gmail.com"),
        ("  spaced@x.io  ", "spaced@x.io"),
        ("ALL@CAPS.ORG", "all@caps.org"),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_normalize_email(raw, expected):
    assert normalize_email(raw) == expected


def test_input_schemas_normalize_email():
    assert Reg(login="alice", password="password123", email="A@B.COM").email == "a@b.com"
    assert MePatch(email=" X@Y.Z ").email == "x@y.z"
    assert UserPatch(email="Q@W.E").email == "q@w.e"
    created = UserCreateAdmin(login="bob", password="password123", email="B@C.D")
    assert created.email == "b@c.d"
