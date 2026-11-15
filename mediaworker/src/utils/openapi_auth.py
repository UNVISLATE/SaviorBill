"""OpenAPI security scheme (только для документации Swagger/ReDoc)."""

from __future__ import annotations

from fastapi.security import HTTPBearer

bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Access-JWT billing (тот же токен, что и для "
    "/api/v1/auth/login в billing).",
)

__all__ = ["bearer_scheme"]
