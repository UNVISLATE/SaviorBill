"""Юнит-тесты реестра настроек (settings_def)."""

import pytest

from utils.settings_def import SETTINGS, by_key, group_keys, seed_defs

pytestmark = pytest.mark.unit


def test_by_key_known_and_unknown():
    assert by_key("smtp.host") is not None
    assert by_key("does.not.exist") is None


def test_seed_defs_only_with_source():
    defs = seed_defs()
    assert all(d.source is not None for d in defs)
    # system.fs_insecure без source не должен попадать в сидинг
    assert all(d.key != "system.fs_insecure" for d in defs)


def test_seed_defs_subset_of_all():
    keys = {d.key for d in SETTINGS}
    assert {d.key for d in seed_defs()}.issubset(keys)


def test_cast_int():
    spec = by_key("smtp.port")
    assert spec is not None
    assert spec.cast("587") == 587
    assert isinstance(spec.cast("587"), int)


def test_cast_bool():
    spec = by_key("smtp.tls")
    assert spec is not None
    assert spec.cast("true") is True
    assert spec.cast("0") is False


def test_secret_flag():
    assert by_key("smtp.pass").secret is True
    assert by_key("smtp.host").secret is False


def test_group_keys():
    role_keys = group_keys("role")
    assert "role.owner" in role_keys
    assert "smtp.host" not in role_keys
