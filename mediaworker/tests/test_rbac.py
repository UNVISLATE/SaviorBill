"""Юнит-тесты проверки иерархических прав mediaworker."""

from utils.rbac import has_perm


def test_none_perms_denied():
    assert has_perm(None, "media.upload") is False
    assert has_perm({}, "media.upload") is False


def test_exact_and_inherited():
    assert has_perm({"media": {"upload": True}}, "media.upload") is True
    # родитель открыт целиком -> дочерние разрешены
    assert has_perm({"media": True}, "media.uploadlarge") is True


def test_wildcard_level():
    assert has_perm({"media": {"*": True}}, "media.uploadlarge") is True


def test_unrelated_denied():
    assert has_perm({"orders": {"read": True}}, "media.upload") is False
