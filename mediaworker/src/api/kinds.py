"""Справочник доступных видов медиа (``kind``) и их целевых форматов/лимитов.

``GET /api/media/kinds`` не требует авторизации для списка ``kind`` (это не
секрет — просто перечень поддерживаемых форматов), но раздел ``limits``
показывает **только собственный эффективный лимит вызывающего** — если
передан валидный Bearer-токен. Специально НЕ раскрываем:

- существование более высокого тарифа (``media.uploadlarge``) и его точные
  числа — иначе обычный пользователь узнает, до какого размера можно давить
  файлами/сколько раз в час, и легче спланировать обход анти-абьюз защиты;
- какие-либо лимиты анонимному вызывающему вообще (без токена — ``limits: null``).
"""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import APIRouter, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials

from utils import security
from utils.config import Config
from utils.convert import _IMAGE_KINDS, _VIDEO_KINDS
from utils.openapi_auth import bearer_scheme
from utils.rbac import has_perm

router = APIRouter()

_PERM_SMALL = "media.upload"
_PERM_LARGE = "media.uploadlarge"


async def _soft_authenticate(request: Request) -> int | None:
    """Как ``_authenticate()`` в upload.py/serve.py, но без 401 — просто ``None``."""
    cfg: Config = request.app.state.cfg
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    try:
        return security.account_id(
            token, cfg.resolve_jwt_secret(), cfg.jwt_alg, cfg.jwt_iss
        )
    except security.InvalidToken:
        return None


@router.get("/kinds")
async def list_kinds(
    request: Request,
    _creds: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict:
    """Список ``kind`` для загрузки + целевые форматы + лимиты **вызывающего**.

    ``_creds`` — только для регистрации Bearer security scheme в OpenAPI
    (см. ``utils/openapi_auth.py``); реальная (опциональная) авторизация —
    в ``_soft_authenticate()`` ниже, токен не обязателен.
    """
    cfg: Config = request.app.state.cfg

    kinds = [
        {"kind": kind, "target": {"ext": "webp", "mime": "image/webp"}}
        for kind in sorted(_IMAGE_KINDS)
    ] + [
        {
            "kind": kind,
            "target": {"ext": "webm", "mime": "video/webm"},
            # Помимо main видео-конверсия даёт постеры (poster-кадры);
            # ``preview_thumb`` — обрезанный мини-постер того же кадра.
            "extra_variants": ["preview", "preview_thumb"],
        }
        for kind in sorted(_VIDEO_KINDS)
    ]

    limits: dict | None = None
    acc_id = await _soft_authenticate(request)
    if acc_id is not None:
        db = request.app.state.db
        acc = await db.account(acc_id)
        if acc is not None and acc.role_key != cfg.role_banned:
            if has_perm(acc.perms, _PERM_LARGE):
                limits = {
                    "perm": _PERM_LARGE,
                    "max_bytes": cfg.max_bytes,
                    "uploads_per_hour": None,  # без часового лимита
                }
            elif has_perm(acc.perms, _PERM_SMALL):
                limits = {
                    "perm": _PERM_SMALL,
                    "max_bytes": cfg.small_max_bytes,
                    "uploads_per_hour": cfg.uploads_per_hour,
                }

    return {"kinds": kinds, "limits": limits}


__all__ = ["router"]

