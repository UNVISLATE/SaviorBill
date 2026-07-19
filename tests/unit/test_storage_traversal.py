"""Юнит-тесты защиты от path traversal в billing ``StorageSvc``."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from utils.storage import StorageSvc

pytestmark = pytest.mark.unit


def _storage(tmp_path) -> StorageSvc:
    cfg = SimpleNamespace(uploads_dir=tmp_path / "uploads", STORAGE_BACKEND="fs")
    return StorageSvc(cfg)


def test_delete_fs_removes_normal_key(tmp_path):
    st = _storage(tmp_path)
    target = tmp_path / "uploads" / "avatars" / "x.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"data")

    st._delete_fs("avatars/x.png")
    assert not target.exists()


def test_delete_fs_ignores_traversal_key(tmp_path):
    """Ключ, указывающий за пределы uploads_dir, должен быть тихо проигнорирован."""
    st = _storage(tmp_path)
    outside = tmp_path / "secret.txt"
    outside.write_text("do not delete me")

    st._delete_fs("../secret.txt")
    assert outside.exists()  # файл вне uploads_dir не тронут
