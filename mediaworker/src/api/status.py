"""Статус конвертации напрямую в mediaworker (``GET /api/media/status/{token}``).

Раньше статус был доступен только через billing
(``GET /api/v1/media/status/{token}``, читает тот же Valkey-ключ + фоллбэк на
БД). Этот роут нужен, если клиент по какой-то причине общается с mediaworker
напрямую (без billing в цепочке) — например, тот же домен смонтирован под
``/api/media/*`` отдельно от billing.

В отличие от billing-варианта здесь нет фоллбэка на Postgres: mediaworker не
владеет схемой ``system_media`` и не пишет туда статус сам, поэтому если ключ
``media:status:{token}`` протух в Valkey (``MEDIA_STATUS_TTL``) — честный 404
(источник истины по готовым медиа — billing, обращайтесь через него).

``jobs`` — сводка недавних/активных запусков ffmpeg этого токена (см.
``utils/proclog.py::jobs_for_token``): ``job_id``/``op``/``status``/``percent``/
``eta_sec``. Billing этого не отдаёт и не обязан — это ephemeral debug-данные
самого mediaworker, а не часть его контракта "готово/не готово" (см.
``docs/media.md``, раздел про realtime-лог и прогресс).

Роут зарегистрирован ДО ``serve_router`` (см. ``api/__init__.py``) — иначе
``GET /{token}`` (catch-all) перехватил бы ``/status/{token}`` так же, как это
уже случилось бы с ``/kinds``.

Авторизация: JWT обязателен, доступ только владельцу токена (``owner_id`` в
статус-хэше, записан на приёме файла в ``upload.py``) либо аккаунту с правом
``admin.media.manage_any`` — раньше знания одного токена было достаточно для
чтения чужого статуса/mime/ошибок (см. AUDIT.md §4.3).
"""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import APIRouter, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials

from utils.authctx import authenticate, authorize
from utils.keys import status_key
from utils.openapi_auth import bearer_scheme
from utils.proclog import ProcLog
from utils.rbac import has_perm

router = APIRouter()

# Доступ к чужому статусу для операторов с правом управления любым медиа —
# то же право, что у preview/thumb-догрузки (см. api/serve.py).
_PERM_MANAGE_ANY = "admin.media.manage_any"


def _may_view_status(owner_id: str | None, acc_id: int, perms: dict | None) -> bool:
    """Может ли ``acc_id`` видеть статус медиа с записанным ``owner_id``.

    ``owner_id`` из старых/аномальных записей может отсутствовать (пустая
    строка в статус-хэше) — в этом случае не блокируем (не было владельца,
    которому мы бы что-то не додали), но такое штатно не создаётся с тех пор,
    как ``upload.py`` требует аутентификации на приёме файла.
    """
    if owner_id is None:
        return True
    if str(acc_id) == owner_id:
        return True
    return has_perm(perms, _PERM_MANAGE_ANY)


@router.get("/status/{token}")
async def media_status(
    request: Request,
    token: str,
    _creds: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict:
    vk: valkey.Valkey = request.app.state.vk
    data = await vk.hgetall(status_key(token))
    if not data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")

    # Owner-check (AUDIT.md §4.3): знания одного лишь токена больше не
    # достаточно — владелец фиксируется на приёме файла (upload.py) и
    # хранится прямо в статус-хэше, поэтому проверка не требует похода в БД
    # (статус существует и для ещё не опубликованных в billing медиа).
    acc_id = await authenticate(request)
    perms, _role = await authorize(request, acc_id)
    if not _may_view_status(data.get("owner_id") or None, acc_id, perms):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "не владелец медиа")

    proc_log: ProcLog = request.app.state.proc_log
    return {
        "token": token,
        "state": data.get("state", "processing"),
        "url": data.get("url") or None,
        "mime": data.get("mime") or None,
        "tag": data.get("tag") or None,
        "error": data.get("error") or None,
        "percent": float(data["percent"]) if data.get("percent") else None,
        "eta_sec": float(data["eta_sec"]) if data.get("eta_sec") else None,
        "jobs": await proc_log.jobs_for_token(token),
    }


__all__ = ["router", "_may_view_status"]
