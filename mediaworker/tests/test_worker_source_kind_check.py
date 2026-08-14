"""Юнит-тест: worker._thumb_replace/_preview_add отклоняют не-изображение как
источник для thumb/preview (defense-in-depth, см. AUDIT.md §4.2 — основная
проверка на приёме файла в api/serve.py, здесь — повторная дешёвая проверка
на случай гонки/повторной постановки задачи из старой очереди)."""

from __future__ import annotations

import pytest

from utils.storage import Storage
from utils.worker import Worker

pytestmark = pytest.mark.asyncio


class _FakeCfg:
    def __init__(self, tmp_path):
        self.uploads_dir = str(tmp_path / "uploads")
        self.media_dir = str(tmp_path / "media")
        self.status_ttl = 3600
        self.backend = "fs"
        self.task_concurrency = 2
        self.task_concurrency_image = 2
        self.task_concurrency_video = 2


class _FakeVk:
    def __init__(self) -> None:
        self.hset_calls: list[tuple[str, dict]] = []

    async def hset(self, key, mapping=None, **_kw):  # noqa: ANN001
        self.hset_calls.append((key, mapping or {}))

    async def expire(self, *_a, **_kw) -> None:
        pass

    async def hget(self, *_a, **_kw):
        return None


class _FakeTaskLog:
    def __init__(self) -> None:
        self.records: list[dict] = []

    async def record(self, **kwargs) -> None:
        self.records.append(kwargs)


class _FakeProcLog:
    async def start_job(self, **_kw) -> str:
        return "job-1"

    async def append(self, *_a, **_kw) -> None:
        pass

    async def finish_job(self, *_a, **_kw) -> None:
        pass


def _make_worker(tmp_path) -> tuple[Worker, _FakeCfg, _FakeVk, _FakeTaskLog]:
    cfg = _FakeCfg(tmp_path)
    vk = _FakeVk()
    task_log = _FakeTaskLog()
    storage = Storage(cfg)
    worker = Worker(
        cfg=cfg, vk=vk, storage=storage, settings=None,
        task_log=task_log, proc_log=_FakeProcLog(), db=None,
    )
    return worker, cfg, vk, task_log


async def test_thumb_replace_rejects_video_source(tmp_path):
    worker, cfg, vk, task_log = _make_worker(tmp_path)
    token = "tok1"
    # MP4 magic bytes (ftyp на смещении 4) — реальная сигнатура видео.
    src = worker.storage.orig_path(f"{token}.thumb_src")
    with open(src, "wb") as f:
        f.write(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16)

    await worker._thumb_replace({"token": token})

    failed = [r for r in task_log.records if r.get("state") == "failed"]
    assert len(failed) == 1
    assert "не является изображением" in failed[0]["detail"]
    # Файл-источник должен быть удалён после отказа (не остаётся мусором).
    assert not __import__("os").path.exists(src)


async def test_preview_add_upload_rejects_video_source(tmp_path):
    worker, cfg, vk, task_log = _make_worker(tmp_path)
    token = "tok3"
    src = worker.storage.orig_path(f"{token}.preview_src")
    with open(src, "wb") as f:
        f.write(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16)

    await worker._preview_add({"token": token, "source": "upload"})

    failed = [r for r in task_log.records if r.get("state") == "failed"]
    assert len(failed) == 1
    assert "не является изображением" in failed[0]["detail"]
