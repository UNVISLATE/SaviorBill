"""Юнит-тесты выбора формата/MIME по виду медиа."""

from utils.convert import target_key


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
