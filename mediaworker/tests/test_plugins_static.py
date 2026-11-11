"""Юнит-тесты раздачи статики UI-бандлов плагинов под /api/media/plugins/*."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.plugins_static as plugins_static
from api import router as media_router


def test_plugin_static_served_under_api_media_prefix(tmp_path, monkeypatch):
    bundle = tmp_path / "plugins" / "demo-plugin" / "admin" / "dist" / "index.js"
    bundle.parent.mkdir(parents=True)
    bundle.write_text("export function mount() {}", encoding="utf-8")

    monkeypatch.setattr(plugins_static._cfg, "DATA_DIR", str(tmp_path))

    test_app = FastAPI()
    test_app.include_router(media_router)
    client = TestClient(test_app)

    res = client.get("/api/media/plugins/demo-plugin/ui/dist/index.js?v=1.0.0")
    assert res.status_code == 200
    assert "application/javascript" in res.headers["content-type"]
    assert "immutable" in res.headers["cache-control"]
    assert res.text == "export function mount() {}"

    # Старый путь без /api/media больше не обслуживается.
    old_res = client.get("/plugins/demo-plugin/ui/dist/index.js")
    assert old_res.status_code == 404


def test_plugin_static_blocks_traversal_and_invalid_slug(tmp_path, monkeypatch):
    admin_dir = tmp_path / "plugins" / "demo-plugin" / "admin"
    admin_dir.mkdir(parents=True)
    (tmp_path / "plugins" / "demo-plugin" / "secret.txt").write_text("secret", encoding="utf-8")

    monkeypatch.setattr(plugins_static._cfg, "DATA_DIR", str(tmp_path))

    test_app = FastAPI()
    test_app.include_router(media_router)
    client = TestClient(test_app)

    bad_slug = client.get("/api/media/plugins/bad!slug/ui/index.js")
    assert bad_slug.status_code == 400

    # FastAPI/httpx нормализует ../ до роутинга или relative_to ловит выход —
    # в любом случае файл за пределами admin/ отдаться не может.
    traversal = client.get("/api/media/plugins/demo-plugin/ui/..%2Fsecret.txt")
    assert traversal.status_code in (403, 404)
