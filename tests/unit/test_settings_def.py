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
    ui_keys = group_keys("ui")
    assert "ui.admin.name" in ui_keys
    assert "smtp.host" not in ui_keys


def test_role_names_not_persisted_as_settings():
    """Имена базовых ролей больше не хранятся как отдельные settings-ключи
    (были мёртвыми "марками", не перечитываемыми после инициализации)."""
    assert by_key("role.owner") is None
    assert not any(d.key.startswith("role.") for d in SETTINGS)


def test_system_flags_locked():
    spec = by_key("system.initialized")
    assert spec is not None
    assert spec.system is True
    assert spec.source is None  # не сидится из ENV, выставляется init-ом вручную


def test_ui_name_protected_but_editable():
    for key in ("ui.admin.name", "ui.client.name"):
        spec = by_key(key)
        assert spec is not None
        assert spec.protected is True
        assert spec.secret is False
        assert spec.source is not None  # сидится при первом запуске
