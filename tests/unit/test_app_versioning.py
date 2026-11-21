"""Тесты вычисления версии приложения и схемы версионирования."""

from types import SimpleNamespace
from pathlib import Path
import pytest

from utils.version import (
    saviorbill_version_scheme,
    resolve_app_version,
    FALLBACK_VERSION,
)


@pytest.mark.unit
def test_version_scheme_exact_tag():
    v = SimpleNamespace(tag="0.2.2", exact=True, dirty=False, distance=0)
    assert saviorbill_version_scheme(v) == "0.2.2"


@pytest.mark.unit
def test_version_scheme_distance():
    v = SimpleNamespace(tag="0.2.2", exact=False, dirty=False, distance=5)
    assert saviorbill_version_scheme(v) == "0.2.2.dev5"


@pytest.mark.unit
def test_version_scheme_dirty_on_tag():
    v = SimpleNamespace(tag="0.2.2", exact=False, dirty=True, distance=0)
    assert saviorbill_version_scheme(v) == "0.2.2.dev0"


@pytest.mark.unit
def test_resolve_app_version_from_baked_file(tmp_path: Path):
    version_file = tmp_path / "VERSION"
    version_file.write_text("0.2.2\n", encoding="utf-8")
    assert resolve_app_version(tmp_path) == "0.2.2"


@pytest.mark.unit
def test_resolve_app_version_fallback_when_empty_or_no_git(tmp_path: Path):
    assert resolve_app_version(tmp_path) == FALLBACK_VERSION
