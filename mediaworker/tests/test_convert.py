"""Юнит-тесты автоопределения вида медиа (detect_kind) и выбора формата/MIME."""

import pytest

from utils.convert import SIGNATURE_READ_BYTES, detect_kind, target_key


def test_image_kind_goes_webp():
    key, mime = target_key("tok123", "image")
    assert key == "tok123.webp"
    assert mime == "image/webp"


def test_video_goes_webm():
    key, mime = target_key("tok123", "video")
    assert key == "tok123.webm"
    assert mime == "video/webm"


def test_unknown_kind_defaults_to_image():
    key, mime = target_key("tok123", "weird")
    assert key.endswith(".webp")
    assert mime == "image/webp"


# ─────────────────────────────────────────────────────────────────────────────
# detect_kind (IMPLEMENTATION_PLAN §11.1 — дешёвая проверка перед ffmpeg +
# автоопределение вида медиа: клиент больше не заявляет ``kind`` сам).
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "header",
    [
        b"\xff\xd8\xff\xe0" + b"\x00" * 12,  # JPEG
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 8,  # PNG
        b"GIF89a" + b"\x00" * 10,  # GIF
        b"BM" + b"\x00" * 14,  # BMP
        b"RIFF\x00\x00\x00\x00WEBPVP8 ",  # RIFF/WEBP
    ],
)
def test_detect_kind_recognizes_image_formats(header):
    assert detect_kind(header[:SIGNATURE_READ_BYTES]) == "image"


@pytest.mark.parametrize(
    "header",
    [
        b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 4,  # MP4 (ftyp на смещении 4)
        b"\x1aE\xdf\xa3" + b"\x00" * 12,  # WebM/MKV (EBML)
        b"OggS" + b"\x00" * 12,  # OGG
        b"RIFF\x00\x00\x00\x00AVI LIST",  # RIFF/AVI
    ],
)
def test_detect_kind_recognizes_video_formats(header):
    assert detect_kind(header[:SIGNATURE_READ_BYTES]) == "video"


def test_detect_kind_returns_none_for_garbage():
    assert detect_kind(b"not a media file!") is None
