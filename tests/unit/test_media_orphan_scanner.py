import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from types import SimpleNamespace

from api.v1.admin.media import router, _sniff_kind_mime


def test_sniff_kind_mime():
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. JPEG
        jpg_file = os.path.join(tmpdir, "test.jpg")
        with open(jpg_file, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 20)
        assert _sniff_kind_mime(jpg_file) == ("image", "image/jpeg")

        # 2. PNG
        png_file = os.path.join(tmpdir, "test.png")
        with open(png_file, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
        assert _sniff_kind_mime(png_file) == ("image", "image/png")

        # 3. WEBP
        webp_file = os.path.join(tmpdir, "test.webp")
        with open(webp_file, "wb") as f:
            f.write(b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 20)
        assert _sniff_kind_mime(webp_file) == ("image", "image/webp")

        # 4. MP4
        mp4_file = os.path.join(tmpdir, "test.mp4")
        with open(mp4_file, "wb") as f:
            f.write(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 20)
        assert _sniff_kind_mime(mp4_file) == ("video", "video/mp4")

        # 5. WebM
        webm_file = os.path.join(tmpdir, "test.webm")
        with open(webm_file, "wb") as f:
            f.write(b"\x1aE\xdf\xa3" + b"\x00" * 20)
        assert _sniff_kind_mime(webm_file) == ("video", "video/webm")

        # 6. SVG
        svg_file = os.path.join(tmpdir, "test.svg")
        with open(svg_file, "wb") as f:
            f.write(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>")
        assert _sniff_kind_mime(svg_file) == ("svg", "image/svg+xml")


@pytest.mark.asyncio
async def test_scan_orphaned_files_registers_new_media():
    from dependencies.auth import get_current_acc
    from dependencies.media import get_media_mngr
    from dependencies.valkey import get_valkey_client
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        media_dir = Path(tmpdir) / "media"
        media_dir.mkdir(parents=True)

        # Create two orphaned files
        hex32_token = "a" * 32
        main_file = media_dir / f"{hex32_token}.webp"
        main_file.write_bytes(b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 50)

        thumb_file = media_dir / f"{hex32_token}.thumb.xyz.webp"
        thumb_file.write_bytes(b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 20)

        standalone_file = media_dir / "dropped_image.png"
        standalone_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 30)

        # Mock session and mngr
        mock_session = AsyncMock()
        # Mock execute returning empty existing rows (no files known)
        mock_result = MagicMock()
        mock_result.__iter__.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.add = MagicMock()

        mock_mngr = MagicMock()
        mock_mngr.s = mock_session

        mock_vk = AsyncMock()
        mock_vk.hset = AsyncMock(return_value=1)

        app = FastAPI()
        app.state.settings = SimpleNamespace(media_dir=media_dir)
        app.include_router(router, prefix="/api/v1/admin/media")

        admin_acc = SimpleNamespace(
            id=1,
            role=SimpleNamespace(name="admin", key="owner", perms={"*": True}),
        )
        app.dependency_overrides[get_current_acc] = lambda: admin_acc
        app.dependency_overrides[get_media_mngr] = lambda: mock_mngr
        app.dependency_overrides[get_valkey_client] = lambda: mock_vk

        client = TestClient(app)
        res = client.post("/api/v1/admin/media/scan-orphans")
        assert res.status_code == 200
        data = res.json()
        assert data["scanned"] == 3
        # Grouped hex token + 1 standalone = 2 recovered items
        assert data["recovered_count"] == 2

        from models.system_media import SystemMediaModel

        # Verify added to DB (2 media models + 1 audit entry)
        media_models = [call[0][0] for call in mock_session.add.call_args_list if isinstance(call[0][0], SystemMediaModel)]
        assert len(media_models) == 2
        added_tokens = [m.token for m in media_models]
        assert hex32_token in added_tokens

        # Verify commit called
        mock_session.commit.assert_called_once()
        # Verify vk hset called for both
        assert mock_vk.hset.call_count >= 2
