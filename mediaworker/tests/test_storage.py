"""Юнит-тесты потокового сохранения оригинала и контроля лимита объёма."""

import os
from types import SimpleNamespace

import pytest

from utils.storage import Storage


def _storage(tmp_path) -> Storage:
    cfg = SimpleNamespace(
        uploads_dir=str(tmp_path / "uploads"),
        media_dir=str(tmp_path / "media"),
        backend="fs",
    )
    return Storage(cfg)


async def _agen(chunks):
    for c in chunks:
        yield c


async def test_save_stream_writes_and_counts(tmp_path):
    st = _storage(tmp_path)
    size = await st.save_stream("tok", _agen([b"aa", b"bbb"]), max_bytes=100)
    assert size == 5
    path = st.orig_path("tok")
    assert os.path.exists(path)
    with open(path, "rb") as f:
        assert f.read() == b"aabbb"


async def test_save_stream_rejects_overflow_and_cleans_up(tmp_path):
    st = _storage(tmp_path)
    with pytest.raises(ValueError):
        await st.save_stream("tok", _agen([b"x" * 6, b"y" * 6]), max_bytes=10)
    # частично записанный файл должен быть удалён
    assert not os.path.exists(st.orig_path("tok"))


async def test_save_stream_skips_empty_chunks(tmp_path):
    st = _storage(tmp_path)
    size = await st.save_stream("tok", _agen([b"", b"ab", b""]), max_bytes=10)
    assert size == 2


# ─────────────────────────────────────────────────────────────────────────────
# Path traversal (AUDIT.md M1) — orig_path/media_fs_path должны отклонять
# попытки выйти за пределы своих каталогов.
# ─────────────────────────────────────────────────────────────────────────────

def test_orig_path_rejects_traversal(tmp_path):
    st = _storage(tmp_path)
    with pytest.raises(ValueError):
        st.orig_path("../../etc/passwd")


def test_media_fs_path_rejects_traversal(tmp_path):
    st = _storage(tmp_path)
    with pytest.raises(ValueError):
        st.media_fs_path("../secrets.txt")


def test_media_fs_path_allows_normal_key(tmp_path):
    st = _storage(tmp_path)
    path = st.media_fs_path("abc123.mp4")
    assert path.endswith("abc123.mp4")
