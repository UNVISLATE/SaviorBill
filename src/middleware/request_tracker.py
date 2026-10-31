"""Middleware сквозного отслеживания запросов (Trace ID), проверки банов и логирования ошибок."""

from __future__ import annotations

import logging
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from services.error_logger import log_request_error
from services.security_monitor import is_ip_banned
from utils.request_context import current_trace_id_ctx, generate_trace_id

log = logging.getLogger("saviorbill.tracker")


class RequestTrackerMiddleware(BaseHTTPMiddleware):
    """Сквозной трекер запросов:

    1. Trace ID: гарантирует стандартный 32-hex идентификатор (W3C Trace Context) для каждого запроса.
    2. IP Ban Gate: пресекает запросы от заблокированных IP с кодом 403 Forbidden.
    3. Журнал ошибок: регистрирует ответы 4xx и 5xx с расширенной телеметрией (задержка, query-параметры, user-agent, referer).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.perf_counter()

        # 1. Извлечение или генерация стандартного 32-hex trace_id
        # Поддерживаем стандартные заголовки: x-trace-id, traceparent (W3C), x-request-id
        trace_id: str | None = None
        raw_header = (
            request.headers.get("x-trace-id")
            or request.headers.get("x-request-id")
        )
        if raw_header and len(raw_header) == 32:
            trace_id = raw_header

        # Если передан W3C traceparent (version-traceid-parentid-flags)
        traceparent = request.headers.get("traceparent")
        if traceparent:
            parts = traceparent.split("-")
            if len(parts) >= 2 and len(parts[1]) == 32:
                trace_id = parts[1]

        if not trace_id:
            trace_id = generate_trace_id()

        request.state.trace_id = trace_id
        token = current_trace_id_ctx.set(trace_id)

        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "")
        referer = request.headers.get("referer", "")
        query_params = str(request.url.query) if request.url.query else ""

        # 2. Проверка временного бана IP (если Valkey инициализирован)
        vk = getattr(request.app.state, "valkey", None)
        if vk is not None:
            # Игнорируем health-чеки, чтобы не ломать probe
            if not request.url.path.startswith("/api/health"):
                banned, reason, ttl = await is_ip_banned(vk, client_ip)
                if banned:
                    resp = JSONResponse(
                        status_code=403,
                        content={
                            "detail": f"IP адрес временно заблокирован: {reason}",
                            "trace_id": trace_id,
                            "ttl_remaining_sec": ttl,
                        },
                        headers={"X-Trace-Id": trace_id, "Retry-After": str(ttl or 60)},
                    )
                    current_trace_id_ctx.reset(token)
                    return resp

        # 3. Выполнение основного обработчика запроса
        exception_type: str | None = None
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            exception_type = type(exc).__name__
            if vk is not None:
                user = getattr(request.state, "user", None)
                await log_request_error(
                    vk,
                    status_code=500,
                    path=request.url.path,
                    method=request.method,
                    client_ip=client_ip,
                    error_detail=str(exc) or "Internal Server Error",
                    query_params=query_params,
                    duration_ms=duration_ms,
                    user_agent=user_agent,
                    referer=referer,
                    user_id=user.id if user else None,
                    user_login=user.login if user else None,
                    user_role=user.role.name if (user and user.role) else None,
                    exception_type=exception_type,
                    trace_id=trace_id,
                )
            current_trace_id_ctx.reset(token)
            raise exc

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Проставляем каноничный X-Trace-Id в ответ
        response.headers["X-Trace-Id"] = trace_id

        # 4. Логирование ответов с ошибками для API
        if response.status_code >= 400 and vk is not None:
            if request.url.path.startswith("/api/"):
                user = getattr(request.state, "user", None)
                user_id = user.id if user else None
                user_login = user.login if user else None
                user_role = user.role.name if (user and user.role) else None

                detail = f"HTTP {response.status_code}"
                await log_request_error(
                    vk,
                    status_code=response.status_code,
                    path=request.url.path,
                    method=request.method,
                    client_ip=client_ip,
                    error_detail=detail,
                    query_params=query_params,
                    duration_ms=duration_ms,
                    user_agent=user_agent,
                    referer=referer,
                    user_id=user_id,
                    user_login=user_login,
                    user_role=user_role,
                    exception_type=exception_type,
                    trace_id=trace_id,
                )

        current_trace_id_ctx.reset(token)
        return response


__all__ = ["RequestTrackerMiddleware"]
