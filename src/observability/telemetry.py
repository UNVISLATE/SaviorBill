"""Наблюдаемость billing: метрики Prometheus + трейсинг OpenTelemetry.

Обе подсистемы — обычные зависимости (см. requirements.txt), импортируются напрямую,
без опциональных заглушек. Ничего не «деградирует молча»: поведение управляется
явными флагами конфигурации.

Метрики
    ``METRICS_ENABLED`` (по умолчанию true) — эндпоинт ``/metrics`` через
    ``prometheus_fastapi_instrumentator``: latency-гистограммы, счётчики запросов,
    размеры тел и число запросов в обработке — с лейблами handler/method/status.
    Готовые дашборды под эти метрики — grafana.com/dashboards/14282.

Трейсинг (OpenTelemetry)
    ``OTEL_ENABLED`` (по умолчанию false) + ``OTEL_EXPORTER_OTLP_ENDPOINT`` — включает
    экспорт спанов по OTLP во внешний коллектор/Jaeger. Автоинструментируются FastAPI
    (входящие HTTP-запросы) и SQLAlchemy (запросы к БД). Когда трейсинг выключен —
    провайдер не ставится и инструментация не применяется (нулевой оверхед).

    При включённом трейсинге ошибки отдают клиенту идентификатор трассы (``trace_id``,
    он же ray id) — в теле ответа и в заголовке ``X-Trace-Id`` — чтобы связать ответ
    с трассой в Jaeger.

Связь трасс между сервисами (billing <-> mediaworker)
    Прямых HTTP-вызовов между сервисами нет — общий контракт только через Valkey
    Streams (``media:tasks``/``media:results``). Чтобы одна трасса в Jaeger покрывала
    оба сервиса, контекст трассы (W3C traceparent) прокидывается через поля
    сообщений стрима: ``inject_carrier`` — на стороне продюсера, ``span_from_carrier``
    — на стороне консьюмера. Обе функции — обычный OpenTelemetry API и не требуют
    проверки флага: без настроенного провайдера они являются no-op (валидного
    контекста трассы просто нет).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.exceptions import HTTPException as StarletteHTTPException

from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter as GRPCSpanExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as HTTPSpanExporter,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

log = logging.getLogger("saviorbill.telemetry")

_tracer = trace.get_tracer("saviorbill")


def _span_exporter(protocol: str, endpoint: str, insecure: bool):
    """Выбрать OTLP-экспортёр спанов по протоколу (grpc | http/protobuf).

    :arg insecure: для grpc — подключаться без TLS (плейнтекст). http/protobuf
        выбирает транспорт по схеме URL, поэтому флаг к нему не применяется.
    """
    if protocol.lower() in ("http", "http/protobuf", "httpprotobuf"):
        return HTTPSpanExporter(endpoint=endpoint)
    return GRPCSpanExporter(endpoint=endpoint, insecure=insecure)


def _configure_tracer_provider(config, service_name: str, service_version: str) -> None:
    """Поставить глобальный TracerProvider с OTLP-экспортёром."""
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


def _install_metrics_auth(app: FastAPI, token: str) -> None:
    """Требовать заголовок ``X-Metrics-Token`` для GET /metrics.

    Дополнительный (не единственный) рубеж защиты — основной способ закрыть
    /metrics от внешнего мира — не проксировать его через реверс-прокси
    (см. deploy/Caddyfile). Несовпадение токена -> 404 (не 401 — эндпоинт не
    должен выдавать сам факт своего существования постороннему).
    """
    import hmac

    @app.middleware("http")
    async def _check_metrics_token(request: Request, call_next):
        if request.url.path == "/metrics":
            provided = request.headers.get("x-metrics-token", "")
            if not hmac.compare_digest(provided, token):
                return JSONResponse({"detail": "not found"}, status_code=404)
        return await call_next(request)


def setup_observability(
    app: FastAPI, config, service_name: str, service_version: str
) -> None:
    """Единая точка настройки наблюдаемости приложения.

    Вызывается один раз после создания :class:`FastAPI`. Включает (по флагам
    конфигурации) метрики Prometheus и трейсинг OpenTelemetry — вместе с
    автоинструментацией входящих HTTP-запросов и обработчиками ошибок с trace_id.

    :arg config: :class:`AppConfig` с полями ``METRICS_ENABLED``/``OTEL_*``.
    :arg service_name: имя сервиса по умолчанию (если не задан ``OTEL_SERVICE_NAME``).
    :arg service_version: версия сервиса (атрибут ресурса трейсинга).
    """
    if config.METRICS_ENABLED:
        # /metrics сам себя не считает (не засоряет метрики опросами Prometheus)
        # и не логируется access-логом uvicorn (см. install_access_log_filter).
        Instrumentator(excluded_handlers=["/metrics"]).instrument(app).expose(
            app, endpoint="/metrics", include_in_schema=False
        )
        if config.METRICS_TOKEN:
            _install_metrics_auth(app, config.METRICS_TOKEN)

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


def instrument_sqlalchemy(engine: AsyncEngine, config) -> None:
    """Автоинструментировать запросы SQLAlchemy (если трейсинг включён)."""
    if config.OTEL_ENABLED:
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)


def current_trace_id() -> str | None:
    """Hex-идентификатор текущей трассы (ray id) либо ``None``, если её нет."""
    ctx = trace.get_current_span().get_span_context()
    if not ctx or not ctx.is_valid:
        return None
    return format(ctx.trace_id, "032x")


def inject_carrier(carrier: dict[str, str] | None = None) -> dict[str, str]:
    """Проставить traceparent текущей трассы в carrier (поля сообщения стрима).

    No-op (не добавит ничего), если активной трассы нет — например, трейсинг
    выключен. Используется продюсером сообщения перед ``xadd``.
    """
    carrier = {} if carrier is None else carrier
    propagate.inject(carrier)
    return carrier


@contextmanager
def span_from_carrier(name: str, carrier: dict[str, str]) -> Iterator[None]:
    """Открыть спан-продолжение трассы, полученной в carrier (сообщение стрима).

    Используется консьюмером сообщения: связывает обработку задачи с трассой,
    в которой она была поставлена в очередь (в другом сервисе). No-op (спан не
    экспортируется), если трейсинг выключен.
    """
    ctx = propagate.extract(carrier)
    with _tracer.start_as_current_span(name, context=ctx):
        yield


__all__ = [
    "setup_observability",
    "instrument_sqlalchemy",
    "current_trace_id",
    "inject_carrier",
    "span_from_carrier",
    "install_access_log_filter",
]
