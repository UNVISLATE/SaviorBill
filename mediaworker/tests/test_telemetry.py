"""Юнит-тесты наблюдаемости mediaworker: метрики, трейсинг, carrier round-trip."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from utils import telemetry


def _cfg(**over) -> SimpleNamespace:
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


def test_setup_observability_disabled_is_noop():
    app = FastAPI()
    telemetry.setup_observability(app, _cfg(), "saviormedia", "1.0")


def test_setup_observability_metrics_enabled_exposes_endpoint():
    app = FastAPI()
    telemetry.setup_observability(app, _cfg(METRICS_ENABLED=True), "saviormedia", "1.0")
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 200


def test_metrics_endpoint_not_counted_in_its_own_metrics():
    app = FastAPI()
    telemetry.setup_observability(app, _cfg(METRICS_ENABLED=True), "saviormedia", "1.0")
    client = TestClient(app)
    client.get("/metrics")
    body = client.get("/metrics").content.decode()
    assert "handler=\"/metrics\"" not in body


def test_metrics_endpoint_requires_token_when_configured():
    app = FastAPI()
    telemetry.setup_observability(
        app, _cfg(METRICS_ENABLED=True, METRICS_TOKEN="s3cr3t"), "saviormedia", "1.0"
    )
    client = TestClient(app)
    assert client.get("/metrics").status_code == 404
    r = client.get("/metrics", headers={"X-Metrics-Token": "s3cr3t"})
    assert r.status_code == 200


def test_access_log_filter_drops_metrics_requests():
    telemetry.install_access_log_filter()
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1,
        '127.0.0.1:0 - "GET /metrics HTTP/1.1" 200', (), None,
    )
    assert telemetry._NoisyEndpointFilter().filter(record) is False


def test_setup_observability_tracing_requires_endpoint():
    with pytest.raises(RuntimeError, match="OTEL_EXPORTER_OTLP_ENDPOINT"):
        telemetry.setup_observability(
            FastAPI(),
            _cfg(OTEL_ENABLED=True, OTEL_EXPORTER_OTLP_ENDPOINT=None),
            "saviormedia",
            "1.0",
        )


def test_current_trace_id_none_outside_span():
    assert telemetry.current_trace_id() is None


def test_inject_carrier_noop_without_active_span():
    assert telemetry.inject_carrier() == {}


def test_span_from_carrier_noop_without_provider():
    with telemetry.span_from_carrier("media.task.convert", {}):
        pass


def test_carrier_round_trip_links_same_trace():
    """inject_carrier внутри спана -> span_from_carrier продолжает ту же трассу
    (это то, что связывает billing и mediaworker в одной трассе Jaeger)."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(InMemorySpanExporter()))
    trace._TRACER_PROVIDER = provider  # noqa: SLF001 — тестовая переустановка провайдера

    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("producer"):
        producer_trace_id = telemetry.current_trace_id()
        carrier = telemetry.inject_carrier()

    assert carrier

    with telemetry.span_from_carrier("media.task.convert", carrier):
        consumer_trace_id = telemetry.current_trace_id()

    assert consumer_trace_id == producer_trace_id
