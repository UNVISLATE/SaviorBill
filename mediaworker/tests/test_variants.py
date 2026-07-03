"""Юнит-тесты именования вариантов конверсии."""

from utils.convert import _thumb_vf, target_key


def test_image_main_key():
    key, mime = target_key("tok123", "image")
    assert key == "tok123.webp"
    assert mime == "image/webp"


def test_video_main_key():
    key, mime = target_key("tok123", "video")
    assert key == "tok123.webm"
    assert mime == "video/webm"


def test_thumb_vf_crops_square():
    vf = _thumb_vf(96)
    assert "scale=96:96" in vf
    assert "crop=96:96" in vf
