"""Middleware сквозного отслеживания запросов (Ray ID), проверки банов и логирования ошибок."""

from __future__ import annotations

import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from services.error_logger import log_request_error
from services.security_monitor import is_ip_banned
from utils.request_context import current_ray_id_ctx, generate_ray_id

log = logging.getLogger("saviorbill.tracker")


class RequestTrackerMiddleware(BaseHTTPMiddleware):
    """Сквозной трекер запросов:

    1. Ray ID: гарантирует уникальный идентификатор каждого входящего запроса.
    2. IP Ban Gate: пресекает запросы от временно заблокированных IP с кодом 403.
    3. Журнал ошибок: регистрирует ответы с кодами 4xx и 5xx для страницы мониторинга в админке.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. Извлечение или генерация Ray ID
        ray_id = (
            request.headers.get("cf-ray")
            or request.headers.get("x-ray-id")
            or request.headers.get("x-request-id")
            or generate_ray_id()
        )
        request.state.ray_id = ray_id
        token = current_ray_id_ctx.set(ray_id)

        client_ip = request.client.host if request.client else "unknown"

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
                            "ray_id": ray_id,
                            "ttl_remaining_sec": ttl,
                        },
                        headers={"X-Ray-Id": ray_id, "Retry-After": str(ttl or 60)},
                    )
                    current_ray_id_ctx.reset(token)
                    return resp

        # 3. Выполнение основного обработчика запроса
        try:
            response = await call_next(request)
        except Exception as exc:
            # Необработанное исключение: логируем как 500
            if vk is not None:
                await log_request_error(
                    vk,
                    status_code=500,
                    path=request.url.path,
                    method=request.method,
                    client_ip=client_ip,
                    error_detail=str(exc) or "Internal Server Error",
                    ray_id=ray_id,
                )
            current_ray_id_ctx.reset(token)
            raise exc

        # Проставляем заголовок Ray ID в ответ
        response.headers["X-Ray-Id"] = ray_id

        # 4. Логирование ответов с ошибками для API
        if response.status_code >= 400 and vk is not None:
            if request.url.path.startswith("/api/"):
                # Получаем пользователя из состояния запроса, если он был аутентифицирован
                user = getattr(request.state, "user", None)
                user_id = user.id if user else None
                user_login = user.login if user else None

                # Краткое описание статуса
                detail = f"HTTP {response.status_code}"
                await log_request_error(
                    vk,
                    status_code=response.status_code,
                    path=request.url.path,
                    method=request.method,
                    client_ip=client_ip,
                    error_detail=detail,
                    user_id=user_id,
                    user_login=user_login,
                    ray_id=ray_id,
                )

        current_ray_id_ctx.reset(token)
        return response
