"""OpenAPI security scheme (только для документации Swagger/ReDoc).

Ручки mediaworker сами разбирают заголовок ``Authorization`` вручную
(``_bearer()``/``_authenticate()`` в ``api/upload.py``/``api/serve.py``) —
это поведение не меняется. Раньше в OpenAPI-схеме вообще не было
зарегистрировано ни одной security-схемы, поэтому в Swagger UI не было
кнопки "Authorize" и замочков на защищённых ручках — их нельзя было
опробовать вручную без ручной правки заголовка через "curl"/browser devtools.

Здесь регистрируется HTTP Bearer security scheme и подключается как
дополнительная (не заменяющая ручной разбор) зависимость на защищённых
ручках — этого достаточно, чтобы FastAPI добавил её в OpenAPI-схему.
"""

from __future__ import annotations

from fastapi.security import HTTPBearer

bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Access-JWT billing (тот же токен, что и для "
    "/api/v1/auth/login в billing).",
)

__all__ = ["bearer_scheme"]
