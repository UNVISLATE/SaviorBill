"""Юнит-тесты наблюдаемости: метрики + трейсинг OpenTelemetry, trace_id в ошибках
и прокидывание контекста трассы через carrier (сообщения Valkey Stream)."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import utils.telemetry as telemetry

pytestmark = pytest.mark.unit


def _cfg(**over) -> SimpleNamespace:
    """Минимальный конфиг с полями METRICS_ENABLED/OTEL_* для setup_observability."""
    base = {
        "METRICS_ENABLED": False,
        "METRICS_TOKEN": None,
        "OTEL_ENABLED": False,
        "OTEL_EXPORTER_OTLP_ENDPOINT": None,
        "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
        "OTEL_EXPORTER_OTLP_INSECURE": True,
        "OTEL_SERVICE_NAME": None,
    }
    base.update(over)
    return SimpleNamespace(**base)


# ─────────────────────────────────────────────────────────────────────────────
# setup_observability
# ─────────────────────────────────────────────────────────────────────────────

def test_setup_observability_disabled_is_noop():
    app = FastAPI()
    telemetry.setup_observability(app, _cfg(), "svc", "1.0")
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 404


def test_setup_observability_metrics_enabled_exposes_endpoint():
    app = FastAPI()
    telemetry.setup_observability(app, _cfg(METRICS_ENABLED=True), "svc", "1.0")
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.content


def test_metrics_endpoint_not_counted_in_its_own_metrics():
    """excluded_handlers=["/metrics"] — опрос Prometheus не засоряет метрики."""
    app = FastAPI()
    telemetry.setup_observability(app, _cfg(METRICS_ENABLED=True), "svc", "1.0")
    client = TestClient(app)
    client.get("/metrics")
    body = client.get("/metrics").content.decode()
    assert '"/metrics"' not in body
    assert "handler=\"/metrics\"" not in body


def test_metrics_endpoint_requires_token_when_configured():
    app = FastAPI()
    telemetry.setup_observability(
        app, _cfg(METRICS_ENABLED=True, METRICS_TOKEN="s3cr3t"), "svc", "1.0"
    )
    client = TestClient(app)
    assert client.get("/metrics").status_code == 404
    assert (
        client.get("/metrics", headers={"X-Metrics-Token": "wrong"}).status_code
        == 404
    )
    r = client.get("/metrics", headers={"X-Metrics-Token": "s3cr3t"})
    assert r.status_code == 200


def test_setup_observability_tracing_enabled_requires_endpoint():
    with pytest.raises(RuntimeError, match="OTEL_EXPORTER_OTLP_ENDPOINT"):
        telemetry.setup_observability(
            FastAPI(),
            _cfg(OTEL_ENABLED=True, OTEL_EXPORTER_OTLP_ENDPOINT=None),
            "svc",
            "1.0",
        )


def test_current_trace_id_none_outside_span():
    assert telemetry.current_trace_id() is None


# ─────────────────────────────────────────────────────────────────────────────
# install_access_log_filter — /metrics не засоряет access-лог uvicorn
# ─────────────────────────────────────────────────────────────────────────────

def test_access_log_filter_drops_metrics_requests():
    logger = logging.getLogger("uvicorn.access")
    telemetry.install_access_log_filter()
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1,
        '127.0.0.1:0 - "GET /metrics HTTP/1.1" 200', (), None,
    )
    assert not any(f.filter(record) for f in logger.filters if isinstance(
        f, telemetry._NoisyEndpointFilter
    ))


def test_access_log_filter_keeps_other_requests():
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1,
        '127.0.0.1:0 - "GET /health HTTP/1.1" 200', (), None,
    )
    assert telemetry._NoisyEndpointFilter().filter(record) is True


# ─────────────────────────────────────────────────────────────────────────────
# inject_carrier / span_from_carrier — прокидывание контекста трассы через Stream
# ─────────────────────────────────────────────────────────────────────────────

def test_inject_carrier_noop_without_active_span():
    carrier = telemetry.inject_carrier()
    assert carrier == {}


def test_span_from_carrier_noop_without_provider():
    """Без настроенного провайдера span_from_carrier не должен падать (no-op)."""
    with telemetry.span_from_carrier("media.task", {}):
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Сквозной тест: trace_id в ответах об ошибках + carrier round-trip при
# включённом трейсинге.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def traced_app(monkeypatch):
    """FastAPI-приложение с включённым трейсингом на in-memory экспортёре спанов."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(InMemorySpanExporter()))
    # Провайдер выставляется один раз на процесс; переопределяем в обход защиты.
    trace._TRACER_PROVIDER = provider  # noqa: SLF001 — тестовая переустановка провайдера

    app = FastAPI()

    @app.get("/boom")
    async def boom():
        raise RuntimeError("kaboom")

    @app.get("/nope")
    async def nope():
        raise HTTPException(status_code=404, detail="not found")

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
    telemetry._install_error_handlers(app)  # noqa: SLF001 — тестовый доступ

    try:
        yield app
    finally:
        FastAPIInstrumentor.uninstrument_app(app)


def test_unhandled_error_carries_trace_id(traced_app):
    client = TestClient(traced_app, raise_server_exceptions=False)
    r = client.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["detail"] == "internal server error"
    assert len(body["trace_id"]) == 32
    assert r.headers["X-Trace-Id"] == body["trace_id"]


def test_http_error_carries_trace_id(traced_app):
    client = TestClient(traced_app, raise_server_exceptions=False)
    r = client.get("/nope")
    assert r.status_code == 404
    body = r.json()
    assert body["detail"] == "not found"
    assert len(body["trace_id"]) == 32
    assert r.headers["X-Trace-Id"] == body["trace_id"]


def test_carrier_round_trip_links_same_trace(traced_app):
    """inject_carrier внутри спана -> span_from_carrier продолжает ту же трассу."""
    from opentelemetry import trace

    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("producer"):
        producer_trace_id = telemetry.current_trace_id()
        carrier = telemetry.inject_carrier()

    assert carrier  # traceparent проставлен

    with telemetry.span_from_carrier("consumer", carrier):
        consumer_trace_id = telemetry.current_trace_id()

    assert consumer_trace_id == producer_trace_id
