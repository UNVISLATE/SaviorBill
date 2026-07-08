"""Юнит-тесты выбора формата/MIME по виду медиа."""

import pytest

from utils.convert import (
    SIGNATURE_READ_BYTES,
    ConvertError,
    SignatureError,
    check_signature,
    target_key,
)


def test_image_kinds_go_webp():
    for kind in ("image", "icon", "avatar"):
        key, mime = target_key("tok123", kind)
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
# check_signature (IMPLEMENTATION_PLAN §11.1 — дешёвая проверка перед ffmpeg)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "kind,header",
    [
        ("image", b"\xff\xd8\xff\xe0" + b"\x00" * 12),  # JPEG
        ("icon", b"\x89PNG\r\n\x1a\n" + b"\x00" * 8),  # PNG
        ("avatar", b"GIF89a" + b"\x00" * 10),  # GIF
        ("image", b"BM" + b"\x00" * 14),  # BMP
        ("image", b"RIFF\x00\x00\x00\x00WEBPVP8 "),  # RIFF/WEBP
    ],
)
def test_check_signature_accepts_known_image_formats(kind, header):
    check_signature(kind, header[:SIGNATURE_READ_BYTES])  # не должно бросать


@pytest.mark.parametrize(
    "header",
    [
        b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 4,  # MP4 (ftyp на смещении 4)
        b"\x1aE\xdf\xa3" + b"\x00" * 12,  # WebM/MKV (EBML)
        b"OggS" + b"\x00" * 12,  # OGG
        b"RIFF\x00\x00\x00\x00AVI LIST",  # RIFF/AVI
    ],
)
def test_check_signature_accepts_known_video_formats(header):
    check_signature("video", header[:SIGNATURE_READ_BYTES])  # не должно бросать


def test_check_signature_rejects_unknown_image():
    with pytest.raises(SignatureError):
        check_signature("image", b"not an image!!!!")


def test_check_signature_rejects_unknown_video():
    with pytest.raises(SignatureError):
        check_signature("video", b"not a video!!!!!")


def test_check_signature_rejects_video_disguised_as_image():
    """Заявлен image, но сигнатура видео (ftyp) — не должна пройти как image."""
    with pytest.raises(SignatureError):
        check_signature("image", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 4)


def test_signature_error_is_convert_error():
    """SignatureError — подкласс ConvertError (существующая обработка ловит обе)."""
    assert issubclass(SignatureError, ConvertError)
