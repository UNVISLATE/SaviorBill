"""Админ: удобная запись UI/брендинг-настроек (/api/v1/admin/settings/ui).

Тонкая обёртка над тем же ``settings`` (key-value), что и ``raw.py`` — просто
избавляет от ручного JSON-квотирования при заполнении ключей ``ui.*``
(например ``ui.admin.logo``, ``ui.client.theme``, см. upd_plan.md, часть 6).
Права/аудит/кэш — те же самые, что и у ``raw.py`` (та же таблица), отдельного
RBAC-права не заводим: кто может редактировать ``settings.raw``, тот может и
через этот роут — просто эргономичнее для UI-полей и bulk-заполнения.

Значение можно передать как:
- JSON-тело (``application/json``) — тип значения сохраняется по смыслу:
  строка сохраняется как есть, любой другой JSON-тип (число/bool/объект/
  массив) сериализуется в JSON-строку (колонка ``settings.value`` — ``Text``);
- form-тело (``application/x-www-form-urlencoded``/``multipart/form-data``) —
  все значения из form приходят строками, сохраняются как есть.

Два эндпоинта:
- ``POST /ui/{key}`` — тело целиком является значением ключа ``ui.{key}``
  (для form — поле ``value``, либо единственное поле формы).
- ``POST /ui`` — тело (JSON-объект или form) — плоский словарь
  ``{"<key>": <value>, ...}``, для каждой пары создаёт/обновляет ``ui.<key>``.
  Ключи могут включать точки для скоупа, например ``"admin.logo"`` →
  ``ui.admin.logo``.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from models.system_settings import SystemSettingsModel
from models.user import UserModel
from schemas.settings_raw import SettingRawOut
from services.audit import audit
from utils.settings_def import by_key

router = APIRouter()


def _serialize(value: Any) -> str | None:
    """Привести произвольное JSON-значение к строке для хранения в ``settings``."""
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value)


async def _extract_single_value(request: Request) -> Any:
    """Достать значение тела запроса для ``POST /ui/{key}`` (JSON или form)."""
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        body = await request.json()
        # Разрешаем и голое значение ({"value": ...} тоже принимаем для удобства).
        if isinstance(body, dict) and "value" in body and len(body) == 1:
            return body["value"]
        return body
    if "form" in ctype:
        form = await request.form()
        if "value" in form:
            return form["value"]
        if len(form) == 1:
            return next(iter(form.values()))
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "form body must contain a single field or a 'value' field",
        )
    raise HTTPException(
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        "expected application/json or form body",
    )


async def _extract_bulk_dict(request: Request) -> dict[str, Any]:
    """Достать словарь ``{key: value}`` тела запроса для ``POST /ui`` (JSON/form)."""
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "body must be a JSON object"
            )
        return body
    if "form" in ctype:
        form = await request.form()
        return dict(form)
    raise HTTPException(
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        "expected application/json or form body",
    )


async def _write_ui_key(
    session: AsyncSession,
    mngr: SystemSettingsMngr,
    request: Request,
    acc: UserModel,
    key: str,
    value: Any,
) -> SettingRawOut:
    """Записать одну пару ``ui.<key> = value`` и вернуть итоговую raw-строку."""
    full_key = f"ui.{key}"
    existing = await session.get(SystemSettingsModel, full_key)
    if existing is not None and existing.is_secret:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "secret system settings cannot be edited here"
        )
    await mngr.set(full_key, _serialize(value), is_secret=False)
    await audit(
        session,
        action="settings.ui.set",
        actor_id=acc.id,
        actor_role=acc.role.name if acc.role else None,
        target_type="setting",
        target_id=full_key,
        ip=request.client.host if request.client else None,
        meta={"created": existing is None},
    )
    row = await session.get(SystemSettingsModel, full_key)
    assert row is not None
    return SettingRawOut.from_model(row, by_key(full_key))


@router.post(
    "/{key}",
    response_model=SettingRawOut,
    summary="Set single ui.* setting",
    description="Body is the value itself (JSON, any type) or a form field "
    "('value' or the single form field); stored as ui.{key}.",
)
async def set_ui_setting(
    request: Request,
    key: str,
    session: AsyncSession = Depends(get_db_session),
    mngr: SystemSettingsMngr = Depends(get_settings_mngr),
    acc: UserModel = Depends(require_perm("settings.raw.edit")),
) -> SettingRawOut:
    value = await _extract_single_value(request)
    out = await _write_ui_key(session, mngr, request, acc, key, value)
    await session.commit()
    return out


@router.post(
    "",
    response_model=list[SettingRawOut],
    summary="Bulk-set ui.* settings",
    description="Body is a flat JSON object {\"key\": value, ...} (or form "
    "fields); each pair is stored as ui.{key} = value. Keys may contain dots "
    "for scoping, e.g. 'admin.logo' -> ui.admin.logo.",
)
async def set_ui_settings_bulk(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    mngr: SystemSettingsMngr = Depends(get_settings_mngr),
    acc: UserModel = Depends(require_perm("settings.raw.edit")),
) -> list[SettingRawOut]:
    data = await _extract_bulk_dict(request)
    if not data:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "body must not be empty"
        )
    out = [
        await _write_ui_key(session, mngr, request, acc, key, value)
        for key, value in data.items()
    ]
    await session.commit()
    return out


__all__ = ["router"]
