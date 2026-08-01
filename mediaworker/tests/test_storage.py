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
# Path traversal — orig_path/media_fs_path должны отклонять
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


# ─────────────────────────────────────────────────────────────────────────────
# link_or_copy — дедуп по содержимому: хардлинк вместо копирования новых байт.
# ─────────────────────────────────────────────────────────────────────────────


async def test_link_or_copy_creates_hardlink_and_removes_tmp(tmp_path):
    st = _storage(tmp_path)
    existing = st.media_fs_path("existing.webp")
    os.makedirs(os.path.dirname(existing), exist_ok=True)
    with open(existing, "wb") as f:
        f.write(b"same-content")

    tmp = os.path.join(str(tmp_path / "uploads"), "new.tmp")
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    with open(tmp, "wb") as f:
        f.write(b"same-content")

    ok = await st.link_or_copy("new.webp", tmp, "existing.webp")
    assert ok is True
    assert not os.path.exists(tmp)  # временный файл удалён
    new_path = st.media_fs_path("new.webp")
    assert os.path.exists(new_path)
    with open(new_path, "rb") as f:
        assert f.read() == b"same-content"
    # хардлинк = тот же inode
    assert os.stat(existing).st_ino == os.stat(new_path).st_ino


async def test_link_or_copy_deleting_one_name_keeps_the_other(tmp_path):
    """Хардлинк — reference counting на уровне ФС: удаление одного имени не
    трогает данные, пока жив второй хардлинк (см. Storage.delete)."""
    st = _storage(tmp_path)
    existing = st.media_fs_path("existing.webp")
    os.makedirs(os.path.dirname(existing), exist_ok=True)
    with open(existing, "wb") as f:
        f.write(b"payload")
    tmp = os.path.join(str(tmp_path / "uploads"), "new.tmp")
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    with open(tmp, "wb") as f:
        f.write(b"payload")
    await st.link_or_copy("new.webp", tmp, "existing.webp")

    await st.delete(["new.webp"])
    assert not os.path.exists(st.media_fs_path("new.webp"))
    assert os.path.exists(existing)
    with open(existing, "rb") as f:
        assert f.read() == b"payload"


async def test_link_or_copy_falls_back_to_false_when_existing_missing(tmp_path):
    st = _storage(tmp_path)
    tmp = os.path.join(str(tmp_path / "uploads"), "new.tmp")
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    with open(tmp, "wb") as f:
        f.write(b"data")

    ok = await st.link_or_copy("new.webp", tmp, "does-not-exist.webp")
    assert ok is False
    assert os.path.exists(tmp)  # не тронут — вызывающий сам сделает put_final


async def test_link_or_copy_s3_backend_always_false():
    st = Storage(
        SimpleNamespace(
            uploads_dir="/tmp/u", media_dir="/tmp/m", backend="s3"
        )
    )
    assert await st.link_or_copy("k", "/tmp/x", "existing") is False
