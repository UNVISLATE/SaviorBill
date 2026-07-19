"""Справочник форматов медиа и правил ``tag`` для клиента/админки.

``GET /api/media/kinds`` не требует авторизации для описания форматов (не
секрет — просто перечень поддерживаемых конверсий), но раздел ``limits``
показывает **только собственный эффективный лимит вызывающего** — если
передан валидный Bearer-токен. Специально НЕ раскрываем:

- существование более высокого тарифа (``media.uploadlarge``) и его точные
  числа — иначе обычный пользователь узнает, до какого размера можно давить
  файлами/сколько раз в час, и легче спланировать обход анти-абьюз защиты;
- какие-либо лимиты анонимному вызывающему вообще (без токена — ``limits: null``).

Вид медиа (``image``/``video``) клиент больше не выбирает при загрузке —
сервер определяет его сам по сигнатуре файла (см. ``utils/convert.py``).
Здесь просто описано, во что конвертируется каждый обнаруженный вид, и
правило для необязательного ``tag`` (метка для UI, не влияет на обработку).
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Security
from fastapi.security import HTTPAuthorizationCredentials

from utils.authctx import soft_authenticate
from utils.config import Config
from utils.openapi_auth import bearer_scheme
from utils.rbac import has_perm
from utils.settings import SettingsResolver

router = APIRouter()

_PERM_SMALL = "media.upload"
_PERM_LARGE = "media.uploadlarge"
_PERM_ADMIN_UNLIMITED = "admin.media.upload"

# Держим в одном месте с upload.py::_TAG_RE (дублирование ради независимости
# модулей — см. пояснение о дублировании auth-хелперов в upload.py/serve.py).
_TAG_PATTERN = "^[A-Za-z0-9]{1,16}$"


@router.get("/kinds")
async def list_kinds(
    request: Request,
    _creds: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict:
    """Форматы медиа + правило ``tag`` + лимиты **вызывающего**.

    ``_creds`` — только для регистрации Bearer security scheme в OpenAPI
    (см. ``utils/openapi_auth.py``); реальная (опциональная) авторизация —
    в ``utils.authctx.soft_authenticate()``, токен не обязателен.
    """
    cfg: Config = request.app.state.cfg
    settings: SettingsResolver = request.app.state.settings

    kinds = [
        {
            "kind": "image",
            "target": {"ext": "webp", "mime": "image/webp"},
            "note": "thumb генерируется только если результат больше "
            "media.small_max_bytes (маленькое фото и так лёгкий webp)",
        },
        {
            "kind": "video",
            "target": {"ext": "webm", "mime": "video/webm"},
            # thumb — один, заменяемый целиком (POST /{token}/thumb);
            # previews — список, 0..N, без лимита по количеству, пополняемый
            # через POST /{token}/preview (ручной кадр либо случайный).
            "extra": {"thumb": "single, replaceable", "previews": "list, unlimited"},
        },
    ]

    limits: dict | None = None
    acc_id = await soft_authenticate(request)
    if acc_id is not None:
        db = request.app.state.db
        acc = await db.account(acc_id)
        if acc is not None:
            if has_perm(acc.perms, _PERM_ADMIN_UNLIMITED):
                limits = {
                    "perm": _PERM_ADMIN_UNLIMITED,
                    "max_bytes": None,  # без ограничения
                    "uploads_per_hour": None,
                }
            elif has_perm(acc.perms, _PERM_LARGE):
                limits = {
                    "perm": _PERM_LARGE,
                    "max_bytes": await settings.max_bytes(),
                    "uploads_per_hour": None,  # без часового лимита
                }
            elif has_perm(acc.perms, _PERM_SMALL):
                limits = {
                    "perm": _PERM_SMALL,
                    "max_bytes": await settings.small_max_bytes(),
                    "uploads_per_hour": await settings.uploads_per_hour(),
                }

    return {
        "kinds": kinds,
        "tag": {
            "pattern": _TAG_PATTERN,
            "max_length": 16,
            "description": "Необязательная метка для UI (латиница+цифры, "
            "не влияет на обработку файла)",
        },
        "limits": limits,
    }


__all__ = ["router"]
