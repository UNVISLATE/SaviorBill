"""Юнит-тесты Фазы 3 (mediaworker): reclaim, preview S3/chunked, GIF thumb dedup, quota cleanup, SVG CSP, WS frames."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.plugins_static as plugins_static
import api.serve as serve_mod
import apiws.v1.media as ws_media
import utils.worker as worker_mod
from api import router as media_router
from utils.convert import Variant
from utils.worker import Worker

# ── 3.5: in-flight задачи не отправляются ложно в DLQ ─────────────────────────


@pytest.mark.asyncio
async def test_reclaim_once_skips_in_flight_messages():
    vk = SimpleNamespace(
        xpending_range=AsyncMock(
            return_value=[{"message_id": "9-1", "times_delivered": 99}]
        ),
        xrange=AsyncMock(),
        xack=AsyncMock(),
        xclaim=AsyncMock(),
        xadd=AsyncMock(),
    )
    cfg = SimpleNamespace(
        task_concurrency=2,
        task_concurrency_image=2,
        task_concurrency_video=1,
        task_stream="media:tasks",
        group="mediaworkers",
        consumer="mw-1",
        task_dlq_stream="media:tasks:dead",
        task_stream_maxlen=100,
        task_max_attempts=3,
        reclaim_min_idle_ms=60_000,
        status_ttl=3600,
        BUS_SIGNING_KEY="",
    )
    w = Worker(cfg=cfg, vk=vk, storage=None, settings=None, task_log=None, proc_log=None, db=None)
    w._in_flight_msgs.add("9-1")

    await w.reclaim_once()
    vk.xack.assert_not_awaited()
    vk.xclaim.assert_not_awaited()
    vk.xadd.assert_not_awaited()


# ── 3.6: _preview_add на S3/.mp4 и chunked add_preview ────────────────────────


@pytest.mark.asyncio
async def test_preview_add_random_uses_real_main_key_and_s3_download(tmp_path, monkeypatch):
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    media_dir = tmp_path / "media"
    media_dir.mkdir()

    cfg = SimpleNamespace(
        task_concurrency=2,
        task_concurrency_image=2,
        task_concurrency_video=1,
        backend="s3",
        uploads_dir=str(uploads_dir),
        media_dir=str(media_dir),
        status_ttl=3600,
    )
    vk = SimpleNamespace(
        hget=AsyncMock(return_value="tok1.mp4"),
        hset=AsyncMock(),
        expire=AsyncMock(),
    )
    storage = SimpleNamespace(
        download=AsyncMock(side_effect=lambda _k, dst: Path(dst).write_bytes(b"mp4data")),
        _safe_unlink=lambda p: Path(p).unlink(missing_ok=True),
    )
    task_log = SimpleNamespace(record=AsyncMock())
    proc_log = SimpleNamespace(start_job=AsyncMock(return_value="j1"), append=AsyncMock(), finish_job=AsyncMock())

    w = Worker(cfg=cfg, vk=vk, storage=storage, settings=None, task_log=task_log, proc_log=proc_log, db=None)
    w._publish = AsyncMock(return_value=("tok1.preview.abc.webp", 123))
    w._emit_result = AsyncMock()
    w._set_op_status = AsyncMock()

    monkeypatch.setattr(worker_mod, "probe_duration", AsyncMock(return_value=10.0))
    monkeypatch.setattr(
        worker_mod,
        "make_preview",
        AsyncMock(return_value=Variant("preview.abc", "tok1.preview.abc.webp", "image/webp")),
    )

    await w._preview_add({"token": "tok1", "source": "random"})

    storage.download.assert_awaited_once()
    assert storage.download.await_args.args[0] == "tok1.mp4"
    # Временный файл должен быть удалён после генерации превью
    assert list(uploads_dir.iterdir()) == []
    vk.hset.assert_awaited()


@pytest.mark.asyncio
async def test_add_preview_detects_chunked_body_without_content_length(monkeypatch):
    app = FastAPI()
    app.include_router(media_router)
    vk = SimpleNamespace(xadd=AsyncMock())
    storage = SimpleNamespace(save_stream=AsyncMock(return_value=32))
    task_log = SimpleNamespace(record=AsyncMock())
    app.state.cfg = SimpleNamespace(task_stream="media:tasks", task_stream_maxlen=100, BUS_SIGNING_KEY="", ban_seconds=60)
    app.state.vk = vk
    app.state.storage = storage
    app.state.task_log = task_log

    monkeypatch.setattr(serve_mod, "_authorize_media_owner", AsyncMock(return_value=(1, True, 1024 * 1024)))
    monkeypatch.setattr(serve_mod, "client_ip", lambda _r: "127.0.0.1")

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
    app_state = app.state

    class _ChunkedRequest:
        headers = {"transfer-encoding": "chunked"}
        app = SimpleNamespace(state=app_state)

        async def stream(self):
            yield png_bytes[:4]
            yield png_bytes[4:]

    await serve_mod.add_preview(_ChunkedRequest(), token="tok9")
    storage.save_stream.assert_awaited_once()
    assert vk.xadd.await_args.args[1]["source"] == "upload"


# ── 3.7 & 3.8: GIF не дублирует thumb; квота чистит file_key; SVG CSP/attachment


@pytest.mark.asyncio
async def test_convert_gif_skips_duplicate_thumb_and_quota_deletes_file_key(tmp_path, monkeypatch):
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    orig = uploads_dir / "tokgif.orig"
    orig.write_bytes(b"GIF89a" + b"\x00" * 32)

    cfg = SimpleNamespace(
        task_concurrency=2,
        task_concurrency_image=2,
        task_concurrency_video=1,
        backend="fs",
        uploads_dir=str(uploads_dir),
        media_dir=str(media_dir),
        status_ttl=3600,
        keep_original=False,
    )
    vk = SimpleNamespace(
        hset=AsyncMock(),
        delete=AsyncMock(),
        expire=AsyncMock(),
    )
    deleted_paths: list[list[str]] = []
    storage = SimpleNamespace(
        orig_path=lambda _t: str(orig),
        delete=AsyncMock(side_effect=lambda p: deleted_paths.append(list(p))),
        _safe_unlink=lambda p: Path(p).unlink(missing_ok=True),
    )
    settings = SimpleNamespace(
        max_bytes=AsyncMock(return_value=10_000_000),
        small_max_bytes=AsyncMock(return_value=10),  # меньше размера main
        quota_image_bytes=AsyncMock(return_value=50),  # меньше итоговых вариантов -> сработает откат
        quota_video_bytes=AsyncMock(return_value=50),
    )
    db = SimpleNamespace(bytes_used_for_owner=AsyncMock(return_value=45))
    task_log = SimpleNamespace(record=AsyncMock())
    proc_log = SimpleNamespace(
        start_job=AsyncMock(return_value="j2"),
        set_stage=AsyncMock(),
        append=AsyncMock(),
        finish_job=AsyncMock(),
    )
    w = Worker(cfg=cfg, vk=vk, storage=storage, settings=settings, task_log=task_log, proc_log=proc_log, db=db)

    make_thumb_mock = AsyncMock()
    monkeypatch.setattr(worker_mod, "make_thumb", make_thumb_mock)
    monkeypatch.setattr(worker_mod, "probe_media", AsyncMock(return_value={}))
    monkeypatch.setattr(
        worker_mod,
        "convert",
        AsyncMock(
            return_value=(
                "image",
                [
                    Variant("main", "tokgif.gif", "image/gif"),
                    Variant("thumb", "tokgif.thumb.webp", "image/webp"),
                ],
            )
        ),
    )
    w._publish = AsyncMock(side_effect=[(v.key, 100) for v in (Variant("main", "tokgif.gif", "image/gif"), Variant("thumb", "tokgif.thumb.webp", "image/webp"))])

    await w._convert({"token": "tokgif", "owner_id": "1"})

    # 3.7: make_thumb не вызывается повторно, т.к. thumb уже есть в variants
    make_thumb_mock.assert_not_awaited()
    # 3.8: при превышении квоты file_key удалён из Valkey
    vk.delete.assert_any_await("media:file:tokgif")
    assert deleted_paths == [["tokgif.gif", "tokgif.thumb.webp"]]


def test_serve_and_plugin_static_enforce_svg_security_headers(tmp_path, monkeypatch):
    svg = tmp_path / "plugins" / "demo" / "admin" / "icon.svg"
    svg.parent.mkdir(parents=True)
    svg.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    monkeypatch.setattr(plugins_static._cfg, "DATA_DIR", str(tmp_path))

    app = FastAPI()
    app.include_router(media_router)
    client = TestClient(app)

    resp = client.get("/api/media/plugins/demo/ui/icon.svg")
    assert resp.status_code == 200
    assert resp.headers.get("content-security-policy") == "default-src 'none'"
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert resp.headers.get("x-content-type-options") == "nosniff"


@pytest.mark.asyncio
async def test_serve_s3_svg_sets_attachment_and_csp(monkeypatch):
    presign_calls: list[dict] = []

    async def _presign(key, expires=3600, *, response_content_disposition=None):
        presign_calls.append({"key": key, "disposition": response_content_disposition})
        return "https://s3.example.test/signed"

    app_state = SimpleNamespace(
        cfg=SimpleNamespace(backend="s3", storage_backend="s3"),
        vk=SimpleNamespace(
            hgetall=AsyncMock(side_effect=[{"state": "ready", "mime": "image/svg+xml"}, {"main": "tok.svg"}]),
        ),
        db=SimpleNamespace(media_variants=AsyncMock(return_value=None)),
        storage=SimpleNamespace(
            inspect=AsyncMock(return_value={"status": "ready"}),
            presign=_presign,
        ),
    )
    req = SimpleNamespace(
        headers={},
        app=SimpleNamespace(state=app_state),
        url=SimpleNamespace(path="/api/media/tok"),
    )
    resp = await serve_mod.serve(req, token="tok")
    assert resp.status_code == 307
    assert presign_calls == [{"key": "tok.svg", "disposition": "attachment"}]
    assert resp.headers.get("content-security-policy") == "default-src 'none'"


# ── 3.9: WS /api/media/mine игнорирует не-dict JSON фреймы ───────────────────


@pytest.mark.asyncio
async def test_ws_mine_ignores_non_dict_json_frames(monkeypatch):
    from fastapi import WebSocketDisconnect

    monkeypatch.setattr(ws_media, "_MAX_TICKS", 4)

    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_text = AsyncMock(
        side_effect=["[1, 2, 3]", '"string"', "null", WebSocketDisconnect()]
    )
    ws.app = SimpleNamespace(state=SimpleNamespace(vk=SimpleNamespace(hgetall=AsyncMock(return_value={}))))

    monkeypatch.setattr(ws_media, "authenticate_ws_payload", AsyncMock(return_value=(1, {"watch": ["tok1"]})))
    monkeypatch.setattr(ws_media, "_owned_tokens", AsyncMock(return_value={"tok1"}))

    # Не должно упасть с AttributeError ('list' object has no attribute 'get')
    await ws_media.my_media_status(ws)
    assert ws.receive_text.await_count == 4
