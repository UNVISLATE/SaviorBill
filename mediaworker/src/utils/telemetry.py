"""Наблюдаемость mediaworker: метрики Prometheus + трейсинг OpenTelemetry.

Зеркало billing-модуля ``utils.telemetry`` (см. его docstring для деталей
дизайна) — сервисы независимо деплоятся и не делят код, но обеспечивают
одинаковый набор наблюдаемости и совместимый механизм связи трасс через
Valkey Streams (``inject_carrier``/``span_from_carrier``).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.exceptions import HTTPException as StarletteHTTPException

from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter as GRPCSpanExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as HTTPSpanExporter,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

log = logging.getLogger("saviormedia.telemetry")

_tracer = trace.get_tracer("saviormedia")


def _span_exporter(protocol: str, endpoint: str, insecure: bool):
    """Выбрать OTLP-экспортёр спанов по протоколу (grpc | http/protobuf)."""
    if protocol.lower() in ("http", "http/protobuf", "httpprotobuf"):
        return HTTPSpanExporter(endpoint=endpoint)
    return GRPCSpanExporter(endpoint=endpoint, insecure=insecure)


def _configure_tracer_provider(config, service_name: str, service_version: str) -> None:
    resource = Resource.create(
        {
            SERVICE_NAME: config.OTEL_SERVICE_NAME or service_name,
            SERVICE_VERSION: service_version,
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = _span_exporter(
        config.OTEL_EXPORTER_OTLP_PROTOCOL,
        config.OTEL_EXPORTER_OTLP_ENDPOINT,
        config.OTEL_EXPORTER_OTLP_INSECURE,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    log.info(
        "OpenTelemetry-трейсинг включён: экспорт %s -> %s",
        config.OTEL_EXPORTER_OTLP_PROTOCOL,
        config.OTEL_EXPORTER_OTLP_ENDPOINT,
    )


def _install_error_handlers(app: FastAPI) -> None:
    """Обработчики ошибок, отдающие клиенту trace_id (ray id) в теле и заголовке."""

    def _with_trace(payload: dict) -> tuple[dict, dict]:
        headers: dict[str, str] = {}
        trace_id = current_trace_id()
        if trace_id:
            payload = {**payload, "trace_id": trace_id}
            headers["X-Trace-Id"] = trace_id
        return payload, headers

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        payload, headers = _with_trace({"detail": exc.detail})
        return JSONResponse(
            payload,
            status_code=exc.status_code,
            headers={**(exc.headers or {}), **headers},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        payload, headers = _with_trace({"detail": exc.errors()})
        return JSONResponse(payload, status_code=422, headers=headers)

    @app.exception_handler(Exception)
    async def _unhandled_exc(request: Request, exc: Exception) -> JSONResponse:
        log.exception("необработанная ошибка запроса")
        payload, headers = _with_trace({"detail": "internal server error"})
        return JSONResponse(payload, status_code=500, headers=headers)


def _install_metrics_guard(app: FastAPI, config) -> None:
    """Защитить GET /metrics лимитом частоты и (опционально) токеном.

    В отличие от billing здесь лимит — не через Valkey (mediaworker обычно
    в одном экземпляре, распределённый sliding-window избыточен), а простой
    process-local счётчик по IP. Если mediaworker когда-нибудь начнёт
    масштабироваться горизонтально — заменить на тот же
    ``security.ratelimit.RateLimiter``, что в billing.
    """
    import hmac
    import time

    window_sec = config.METRICS_RATE_LIMIT_WINDOW
    max_hits = config.METRICS_RATE_LIMIT_MAX
    hits: dict[str, list[float]] = {}

    @app.middleware("http")
    async def _guard_metrics(request: Request, call_next):
        if request.url.path == "/metrics":
            ident = request.client.host if request.client else "unknown"
            now = time.monotonic()
            recent = [t for t in hits.get(ident, []) if now - t < window_sec]
            recent.append(now)
            hits[ident] = recent
            if len(recent) > max_hits:
                return JSONResponse(
                    {"detail": "too many requests"}, status_code=429
                )
            if config.METRICS_TOKEN:
                provided = request.headers.get("x-metrics-token", "")
                if not hmac.compare_digest(provided, config.METRICS_TOKEN):
                    return JSONResponse({"detail": "not found"}, status_code=404)
        return await call_next(request)


def setup_observability(
    app: FastAPI, config, service_name: str, service_version: str
) -> None:
    """Единая точка настройки наблюдаемости приложения (метрики + трейсинг)."""
    if config.METRICS_ENABLED:
        # /metrics сам себя не считает и не логируется access-логом uvicorn
        # (см. install_access_log_filter).
        Instrumentator(excluded_handlers=["/metrics"]).instrument(app).expose(
            app, endpoint="/metrics", include_in_schema=False
        )
        _install_metrics_guard(app, config)

    if not config.OTEL_ENABLED:
        return
    if not config.OTEL_EXPORTER_OTLP_ENDPOINT:
        raise RuntimeError(
            "OTEL_ENABLED=true, но OTEL_EXPORTER_OTLP_ENDPOINT не задан — "
            "укажите OTLP-эндпоинт коллектора/Jaeger."
        )

    _configure_tracer_provider(config, service_name, service_version)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/metrics")
    _install_error_handlers(app)


class _NoisyEndpointFilter(logging.Filter):
    """Отфильтровать access-логи uvicorn по опрашиваемым служебным путям.

    /metrics дёргается Prometheus раз в несколько секунд — без фильтра он
    забивает лог шумом и мешает искать реальные запросы.
    """

    def __init__(self, paths: tuple[str, ...] = ("/metrics",)) -> None:
        super().__init__()
        self._paths = paths

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(path in message for path in self._paths)


def install_access_log_filter() -> None:
    """Убрать /metrics из access-лога uvicorn (``uvicorn.access``)."""
    logging.getLogger("uvicorn.access").addFilter(_NoisyEndpointFilter())


def current_trace_id() -> str | None:
    """Hex-идентификатор текущей трассы (ray id) либо ``None``, если её нет."""
    ctx = trace.get_current_span().get_span_context()
    if not ctx or not ctx.is_valid:
        return None
    return format(ctx.trace_id, "032x")


def instrument_valkey(client, config) -> None:
    """Открывать спан на каждую команду Valkey (см. billing ``telemetry/otel.py``

    для полного объяснения, почему не годится готовый
    ``opentelemetry-instrumentation-redis`` — та же причина здесь: клиент
    ``valkey`` не является классом пакета ``redis``, который патчит
    инструментатор."""
    if not config.OTEL_ENABLED:
        return
    if getattr(client, "_otel_instrumented", False):
        return
    original = client.execute_command

    async def _traced_execute_command(command, *args, **kwargs):
        with _tracer.start_as_current_span(f"valkey.{str(command).lower()}") as span:
            span.set_attribute("db.system", "valkey")
            span.set_attribute("db.operation", str(command))
            return await original(command, *args, **kwargs)

    client.execute_command = _traced_execute_command
    client._otel_instrumented = True


def inject_carrier(carrier: dict[str, str] | None = None) -> dict[str, str]:
    """Проставить traceparent текущей трассы в carrier (поля сообщения стрима).

    No-op без активной трассы (трейсинг выключен). Используется продюсером
    сообщения (``xadd``) перед отправкой в ``media:tasks``/``media:results``.
    """
    carrier = {} if carrier is None else carrier
    propagate.inject(carrier)
    return carrier


@contextmanager
def span_from_carrier(name: str, carrier: dict[str, str]) -> Iterator[None]:
    """Открыть спан-продолжение трассы, полученной в carrier (сообщение стрима).

    Используется консьюмером сообщения — связывает обработку с трассой,
    в которой задача была поставлена в очередь (billing или mediaworker).
    """
    ctx = propagate.extract(carrier)
    with _tracer.start_as_current_span(name, context=ctx):
        yield


__all__ = [
    "setup_observability",
    "instrument_valkey",
    "current_trace_id",
    "inject_carrier",
    "span_from_carrier",
    "install_access_log_filter",
]
