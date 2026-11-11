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


# ─────────────────────────────────────────────────────────────────────────────
# sniff_and_rewind (AUDIT.md §4.1/§4.2) — читать заголовок для определения
# типа файла ДО записи на диск, не теряя прочитанные байты.
# ─────────────────────────────────────────────────────────────────────────────


async def _achunks(chunks: list[bytes]):
    for c in chunks:
        yield c


@pytest.mark.asyncio
async def test_sniff_and_rewind_returns_header_and_full_stream():
    from utils.convert import sniff_and_rewind

    chunks = [b"\xff\xd8\xff\xe0", b"rest-of-jpeg-data", b"-more"]
    header, body = await sniff_and_rewind(_achunks(chunks), want=4)
    assert header == b"\xff\xd8\xff\xe0"
    collected = b""
    async for c in body:
        collected += c
    assert collected == b"".join(chunks)


@pytest.mark.asyncio
async def test_sniff_and_rewind_handles_stream_shorter_than_want():
    from utils.convert import sniff_and_rewind

    chunks = [b"ab"]
    header, body = await sniff_and_rewind(_achunks(chunks), want=16)
    assert header == b"ab"
    collected = b""
    async for c in body:
        collected += c
    assert collected == b"ab"


@pytest.mark.asyncio
async def test_sniff_and_rewind_detects_kind_from_first_bytes():
    from utils.convert import sniff_and_rewind

    # PNG magic split across two small chunks — header must still assemble.
    chunks = [b"\x89PN", b"G\r\n\x1a\n", b"restofpngdata"]
    header, body = await sniff_and_rewind(_achunks(chunks), want=SIGNATURE_READ_BYTES)
    assert detect_kind(header) == "image"
    collected = b""
    async for c in body:
        collected += c
    assert collected == b"".join(chunks)


# ─────────────────────────────────────────────────────────────────────────────
# sanitize_paths (AUDIT.md §4.4) — маскировать абсолютные пути сервера в
# сыром выводе ffmpeg/ffprobe перед показом клиенту.
# ─────────────────────────────────────────────────────────────────────────────


def test_sanitize_paths_masks_known_directories():
    from utils.convert import sanitize_paths

    text = "Input #0, mov: /srv/media/uploads/abc.orig -> /srv/media/final/abc.webm"
    out = sanitize_paths(text, "/srv/media/uploads", "/srv/media/final")
    assert "/srv/media/uploads" not in out
    assert "/srv/media/final" not in out
    assert "<mediaworker>" in out


def test_sanitize_paths_noop_without_match():
    from utils.convert import sanitize_paths

    text = "frame=  10 fps=25 q=28.0 size=100kB time=00:00:01.00 bitrate=800kbit/s"
    assert sanitize_paths(text, "/srv/media/uploads") == text


def test_sanitize_paths_ignores_empty_dirs():
    from utils.convert import sanitize_paths

    assert sanitize_paths("hello", "", None) == "hello"


def test_is_svg_requires_svg_tag_not_plain_xml():
    from utils.convert import is_svg

    assert is_svg(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>') is True
    assert is_svg(b'<?xml version="1.0"?><svg width="10" height="10"></svg>') is True
    assert is_svg(b'<?xml version="1.0"?><root><item>1</item></root>') is False
    assert is_svg(b"<html><body>hello</body></html>") is False


@pytest.mark.asyncio
async def test_convert_video_libx264_switches_webm_to_mp4(tmp_path, monkeypatch):
    import utils.convert as convert_mod
    from utils.convert import Variant, convert_video

    src = tmp_path / "in.mp4"
    src.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16)
    cfg = type("Cfg", (), {"webm_crf": 32})()
    cmds: list[list[str]] = []

    async def fake_run(cmd, **_kw):
        cmds.append(cmd)

    monkeypatch.setattr(convert_mod, "_run", fake_run)
    monkeypatch.setattr(
        convert_mod,
        "make_thumb",
        lambda *_a, **_kw: _async_val(Variant("thumb", "tok.thumb.webp", "image/webp")),
    )
    monkeypatch.setattr(
        convert_mod,
        "make_preview",
        lambda *_a, **_kw: _async_val(Variant("preview.1", "tok.preview.1.webp", "image/webp")),
    )

    variants = await convert_video(
        cfg,
        str(src),
        str(tmp_path),
        "tok",
        video_codec="libx264",
        format_choice="webm",
    )
    assert variants[0].key == "tok.mp4"
    assert variants[0].mime == "video/mp4"
    assert cmds[0][-1].endswith("tok.mp4")


async def _async_val(val):
    return val
