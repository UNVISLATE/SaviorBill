"""Unit tests for Service Attachment media schema variants (thumb and previews)."""

from unittest.mock import MagicMock
import pytest
from schemas.media import Attachment


@pytest.mark.unit
def test_attachment_from_model_with_variants():
    mock_media = MagicMock()
    mock_media.token = "tok_video_123"
    mock_media.kind = "video"
    mock_media.mime = "video/mp4"
    mock_media.status = "ready"
    mock_media.meta = {"name": "Demo Video.mp4"}
    mock_media.variants = {
        "thumb": {
            "mime": "image/webp",
            "size": 1234,
            "url": "/api/media/tok_video_123.thumb",
            "artifact_status": "ready",
        },
        "previews": [
            {
                "mime": "image/webp",
                "size": 5678,
                "url": "/api/media/tok_video_123.preview_0",
                "artifact_status": "ready",
            },
            {
                "mime": "image/webp",
                "size": 5679,
                "url": "/api/media/tok_video_123.preview_1",
                "artifact_status": "ready",
            },
        ],
    }

    mock_attachment = MagicMock()
    mock_attachment.id = 10
    mock_attachment.media_id = 42
    mock_attachment.tag = "card"
    mock_attachment.position = 0
    mock_attachment.media = mock_media

    att = Attachment.from_model(mock_attachment)
    assert att.id == 10
    assert att.media_id == 42
    assert att.token == "tok_video_123"
    assert att.name == "Demo Video.mp4"
    assert att.kind == "video"
    assert att.tag == "card"
    assert att.position == 0
    assert att.url == "/api/media/tok_video_123"
    assert att.thumb is not None
    assert att.thumb.url == "/api/media/tok_video_123.thumb"
    assert len(att.previews) == 2
    assert att.previews[0].url == "/api/media/tok_video_123.preview_0"
    assert att.previews[1].url == "/api/media/tok_video_123.preview_1"


@pytest.mark.unit
def test_attachment_from_model_without_variants():
    mock_media = MagicMock()
    mock_media.token = "tok_img_999"
    mock_media.kind = "image"
    mock_media.mime = "image/png"
    mock_media.status = "ready"
    mock_media.meta = None
    mock_media.variants = None

    mock_attachment = MagicMock()
    mock_attachment.id = 11
    mock_attachment.media_id = 99
    mock_attachment.tag = "banner"
    mock_attachment.position = 1
    mock_attachment.media = mock_media

    att = Attachment.from_model(mock_attachment)
    assert att.thumb is None
    assert att.previews == []
    assert att.name is None
