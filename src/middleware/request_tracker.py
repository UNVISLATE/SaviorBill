"""Middleware сквозного отслеживания запросов (Trace ID), проверки банов и логирования ошибок."""

from __future__ import annotations

import logging
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from services.error_logger import log_request_error
from services.security_monitor import is_ip_banned, ban_ip
from utils.request_context import current_trace_id_ctx, generate_trace_id

log = logging.getLogger("saviorbill.tracker")


def _extract_user_telemetry(request: Request) -> tuple[int | None, str | None, str | None]:
    """Безопасно извлечь (id, login, role_name) из ``request.state`` или токена запроса."""
    snapshot = getattr(request.state, "user_snapshot", None)
    if isinstance(snapshot, tuple) and len(snapshot) == 3 and snapshot[0] is not None:
        return snapshot
    user = getattr(request.state, "user", None)
    if user:
        role = getattr(user, "role", None)
        return (
            getattr(user, "id", None),
            getattr(user, "login", None),
            getattr(role, "name", None) if role else None,
        )

    # Запасной путь: если аутентификация упала (например, 401 истёк токен),
    # извлекаем пользователя из переданного JWT без верификации подписи,
    # проверяя access токен, refresh токен и cookie sb_refresh,
    # чтобы в системном журнале ошибок не висело ложное «Анонимный клиент».
    try:
        import jwt as pyjwt
        candidate_tokens: list[str] = []
        auth_hdr = request.headers.get("authorization") or ""
        if auth_hdr.lower().startswith("bearer "):
            candidate_tokens.append(auth_hdr[7:].strip())

        cookies = getattr(request, "cookies", {}) or {}
        if "sb_access" in cookies:
            candidate_tokens.append(cookies["sb_access"])
        if "sb_refresh" in cookies:
            candidate_tokens.append(cookies["sb_refresh"])

        try:
            query_token = request.query_params.get("token") or request.query_params.get("access_token")
            if query_token:
                candidate_tokens.append(query_token)
        except Exception:
            pass

        for raw_token in candidate_tokens:
            if not raw_token:
                continue
            try:
                unverified = pyjwt.decode(
                    raw_token,
                    options={
                        "verify_signature": False,
                        "verify_exp": False,
                        "verify_aud": False,
                        "verify_iss": False,
                    },
                )
                sub = unverified.get("sub")
                user_id = int(sub) if sub and str(sub).isdigit() else None
                login = unverified.get("login")
                role = unverified.get("role")
                if user_id is not None:
                    login_display = login or f"user_{user_id}"
                    return (user_id, login_display, role)
            except Exception:
                continue
    except Exception:
        pass

    app_token = request.headers.get("x-app-token")
    if app_token:
        parts = app_token.split("_")
        tag = parts[2] if len(parts) >= 3 else "token"
        return (None, f"app:{tag}", "app_token")

    return None, None, None


class RequestTrackerMiddleware(BaseHTTPMiddleware):
    """Сквозной трекер запросов."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.perf_counter()

        # 1. Извлечение или генерация стандартного 32-hex trace_id
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

        # 1.1. Защита от OOM DoS: проверка размера тела запроса (лимит 16MB)
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > 16 * 1024 * 1024:
            current_trace_id_ctx.reset(token)
            return JSONResponse(
                status_code=413,
                content={"detail": "Payload too large (limit: 16MB)", "trace_id": trace_id},
                headers={"X-Trace-Id": trace_id},
            )

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
                user_id, user_login, user_role = _extract_user_telemetry(request)
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
                    user_id=user_id,
                    user_login=user_login,
                    user_role=user_role,
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
                user_id, user_login, user_role = _extract_user_telemetry(request)

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

                # 5. Защита от сканеров уязвимостей (404 Error-Rate Throttling)
                # Обычный пользователь генерирует 0-2 ошибки 404; боты-сканеры (DirBuster, Nikto) генерируют 25+
                if response.status_code == 404:
                    try:
                        scan_key = f"security:scan_404:{client_ip}"
                        cnt = await vk.incr(scan_key)
                        if cnt == 1:
                            await vk.expire(scan_key, 60)
                        if cnt >= 25:
                            await ban_ip(
                                vk,
                                ip=client_ip,
                                duration_sec=900,
                                reason="Аномальное сканирование API: 25+ ошибок 404 за 60с (DirBuster/Bot scan)",
                                trace_id=trace_id,
                            )
                    except Exception as err:
                        log.warning("error tracking 404 scan counter: %s", err)

        current_trace_id_ctx.reset(token)
        return response


__all__ = ["RequestTrackerMiddleware"]
