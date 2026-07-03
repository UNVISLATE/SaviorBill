"""Инициализация OpenTelemetry (трейсинг + метрики) и JSON-логирование.

Все настройки — через ENV. Если ``OTEL_EXPORTER_OTLP_ENDPOINT`` пуст — трейсинг в
режиме no-op (нулевые накладные). ``METRICS_ENABLED=false`` — ``/metrics`` отдаёт 404.

Тяжёлые зависимости (opentelemetry, prometheus_client) опциональны: их отсутствие
не ломает приложение — модуль корректно деградирует до no-op.
"""

from __future__ import annotations

import logging
import os

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False

try:
    from prometheus_client import make_asgi_app, REGISTRY

    _HAS_PROMETHEUS = True
except ImportError:
    _HAS_PROMETHEUS = False


def setup_telemetry(service_name: str) -> None:
    """Инициализировать трейсинг и метрики. no-op, если не сконфигурировано."""
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if not endpoint or not _HAS_OTEL:
        return
    provider = TracerProvider()
    exporter = OTLPSpanExporter(endpoint=endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)


def setup_logging(service_name: str) -> None:
    """JSON-логирование при ``LOG_FORMAT=json``, иначе — обычный текст."""
    log_format = os.getenv("LOG_FORMAT", "text").lower()
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    if log_format == "json":
        try:
            import json_log_formatter

            formatter = json_log_formatter.JSONFormatter()
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            logging.basicConfig(handlers=[handler], level=level, force=True)
            return
        except ImportError:
            pass
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )


def metrics_app():
    """ASGI-приложение метрик Prometheus или None, если недоступно/выключено."""
    if _HAS_PROMETHEUS and os.getenv("METRICS_ENABLED", "true").lower() != "false":
        return make_asgi_app()
    return None


__all__ = ["setup_telemetry", "setup_logging", "metrics_app"]
