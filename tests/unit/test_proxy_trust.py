"""Юнит-тесты доверия X-Forwarded-For (IMPLEMENTATION_PLAN §10).

Проверяем: (1) парсинг ``TRUSTED_PROXIES`` в конфиге, (2) поведение
``ProxyHeadersMiddleware`` — заголовок учитывается только когда прямой TCP-peer
входит в список доверенных прокси, иначе `request.client.host` остаётся
реальным адресом подключения (защита от спуфинга клиентом напрямую).
"""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from core.config import AppConfig

pytestmark = pytest.mark.unit


# ─────────────────────────────────────────────────────────────────────────────
# AppConfig.trusted_proxies_list
# ─────────────────────────────────────────────────────────────────────────────

def test_trusted_proxies_default_empty():
    cfg = AppConfig(TRUSTED_PROXIES="")
    assert cfg.trusted_proxies_list == []


def test_trusted_proxies_parses_csv():
    cfg = AppConfig(TRUSTED_PROXIES="10.0.0.1, 10.0.0.2 ,10.0.0.3")
    assert cfg.trusted_proxies_list == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]


# ─────────────────────────────────────────────────────────────────────────────
# ProxyHeadersMiddleware: спуфинг X-Forwarded-For не должен работать без доверия
# ─────────────────────────────────────────────────────────────────────────────

async def _whoami(request: Request) -> JSONResponse:
    return JSONResponse({"client": request.client.host if request.client else None})


def _make_app(trusted_hosts) -> Starlette:
    app = Starlette(routes=[Route("/whoami", _whoami)])
    return ProxyHeadersMiddleware(app, trusted_hosts=trusted_hosts)


def test_xff_ignored_when_no_trusted_proxies():
    """Без доверенных прокси заголовок полностью игнорируется — реальный peer."""
    app = _make_app(trusted_hosts=[])  # пустой список — никому не доверяем
    client = TestClient(app, client=("203.0.113.9", 12345))
    resp = client.get("/whoami", headers={"X-Forwarded-For": "1.2.3.4"})
    assert resp.json()["client"] == "203.0.113.9"


def test_xff_honored_only_from_trusted_peer():
    """Прямой peer в доверенном списке — X-Forwarded-For учитывается."""
    app = _make_app(trusted_hosts=["203.0.113.9"])
    client = TestClient(app, client=("203.0.113.9", 12345))
    resp = client.get("/whoami", headers={"X-Forwarded-For": "1.2.3.4"})
    assert resp.json()["client"] == "1.2.3.4"


def test_xff_not_honored_from_untrusted_peer():
    """Тот же заголовок, но прямой peer НЕ в доверенном списке — игнор."""
    app = _make_app(trusted_hosts=["198.51.100.1"])  # другой прокси, не наш peer
    client = TestClient(app, client=("203.0.113.9", 12345))
    resp = client.get("/whoami", headers={"X-Forwarded-For": "1.2.3.4"})
    assert resp.json()["client"] == "203.0.113.9"
