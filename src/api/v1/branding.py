"""Публичный брендинг UI и настройки клиентского/админского интерфейса."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.settings_def import by_key
from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from models.user import UserModel
from services.audit import audit
from services.fx import DEFAULT_CURRENCY

router = APIRouter(prefix="/api/v1/branding", tags=["branding"])

_CACHE_CONTROL = "no-cache, must-revalidate"



def _unflatten_dict(flat: dict[str, Any]) -> dict[str, Any]:
    """Развернуть словарь с точечными ключами ('mediadialog.enabled') в иерархическое дерево."""
    result: dict[str, Any] = {}
    for key, value in flat.items():
        parts = key.split(".")
        curr = result
        for part in parts[:-1]:
            if part not in curr or not isinstance(curr[part], dict):
                curr[part] = {}
            curr = curr[part]
        curr[parts[-1]] = value
    return result


def _flatten_dict(nested: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Схлопнуть вложенный словарь в плоский словарь с точечными ключами."""
    result: dict[str, Any] = {}
    for key, value in nested.items():
        full_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            result.update(_flatten_dict(value, full_key))
        else:
            result[full_key] = value
    return result


def _serialize(value: Any) -> str | None:
    """Привести произвольное значение к строке для сохранения в БД settings."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _media_url(token: str) -> str:
    """Относительный URL отдачи медиа (обслуживает Caddy/mediaworker)."""
    return f"/api/media/{token}"


def _build_body(scope: str, raw: dict[str, str]) -> dict:
    """Собрать тело ответа брендинга и настроек UI из сырых записей settings."""
    logo = raw.get(f"ui.{scope}.logo")
    favicon = raw.get(f"ui.{scope}.favicon")
    theme_raw = raw.get(f"ui.{scope}.theme")

    prefix = f"ui.{scope}.settings."
    flat_settings: dict[str, Any] = {}
    for k, v in raw.items():
        if k.startswith(prefix):
            sub_k = k[len(prefix):]
            sdef = by_key(k)
            if sdef and v is not None:
                try:
                    flat_settings[sub_k] = sdef.cast(v)
                except Exception:
                    flat_settings[sub_k] = v
            else:
                flat_settings[sub_k] = v

    settings_tree = _unflatten_dict(flat_settings)

    ver = hashlib.md5(
        f"{logo}:{favicon}:{raw.get(f'ui.{scope}.name')}:{theme_raw}:{json.dumps(settings_tree, sort_keys=True)}".encode()
    ).hexdigest()[:8]

    return {
        "name": raw.get(f"ui.{scope}.name"),
        "logo_url": f"{_media_url(logo)}?v={ver}" if logo else None,
        "favicon_url": f"{_media_url(favicon)}?v={ver}" if favicon else None,
        "theme": json.loads(theme_raw) if theme_raw else {},
        "settings": settings_tree,
        "version": ver,
    }


class BrandingUpdateIn(BaseModel):
    name: str | None = None
    logo: str | None = None
    favicon: str | None = None
    theme: dict[str, Any] | None = None
    settings: dict[str, Any] | None = None


@router.get(
    "/{scope}",
    response_model=None,
    summary="Public branding and UI settings",
    description="Aggregates ui.{scope}.* settings and nested settings tree into a flat JSON body.",
)
async def get_branding(
    scope: Literal["admin", "client"],
    request: Request,
    response: Response,
    mngr: SystemSettingsMngr = Depends(get_settings_mngr),
) -> dict | None:
    raw = await mngr.get_group(f"ui.{scope}.")
    body = _build_body(scope, raw)
    body["currency"] = (await mngr.get("billing.currency")) or DEFAULT_CURRENCY
    etag = f'W/"{hashlib.md5(json.dumps(body, sort_keys=True).encode()).hexdigest()}"'

    if request.headers.get("if-none-match") == etag:
        response.status_code = status.HTTP_304_NOT_MODIFIED
        response.headers["ETag"] = etag
        response.headers["Cache-Control"] = _CACHE_CONTROL
        return None

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return body


@router.put(
    "/{scope}",
    response_model=None,
    summary="Update UI branding and settings",
    description="Updates ui.{scope}.* settings, including branding and nested ui.{scope}.settings.* tree.",
)
async def update_branding(
    request: Request,
    scope: Literal["admin", "client"],
    body: BrandingUpdateIn,
    session: AsyncSession = Depends(get_db_session),
    mngr: SystemSettingsMngr = Depends(get_settings_mngr),
    acc: UserModel = Depends(require_perm("settings.raw.edit")),
) -> dict:
    updated_fields: list[str] = []

    if body.name is not None:
        await mngr.set(f"ui.{scope}.name", body.name, is_secret=False)
        updated_fields.append("name")

    if body.logo is not None:
        await mngr.set(f"ui.{scope}.logo", body.logo if body.logo else None, is_secret=False)
        updated_fields.append("logo")

    if body.favicon is not None:
        await mngr.set(f"ui.{scope}.favicon", body.favicon if body.favicon else None, is_secret=False)
        updated_fields.append("favicon")

    if body.theme is not None:
        theme_str = json.dumps(body.theme) if body.theme else None
        await mngr.set(f"ui.{scope}.theme", theme_str, is_secret=False)
        updated_fields.append("theme")

    if body.settings is not None:
        flat = _flatten_dict(body.settings)
        for sub_k, val in flat.items():
            full_k = f"ui.{scope}.settings.{sub_k}"
            sdef = by_key(full_k)
            raw_str = _serialize(val)
            if sdef and raw_str is not None:
                try:
                    casted = sdef.cast(raw_str)
                    serialized = _serialize(casted)
                except Exception as e:
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                        f"Некорректное значение для настройки '{sub_k}': {e}",
                    )
            else:
                serialized = raw_str

            if sub_k == "mediadialog.default.video_preset" and raw_str:
                if raw_str.lower() not in {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"}:
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                        f"Недопустимый пресет видео: {raw_str}",
                    )
            elif sub_k == "mediadialog.default.audio_bitrate" and raw_str:
                if not re.match(r"^\d{2,4}k$", raw_str.strip().lower()):
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                        f"Недопустимый битрейт аудио: {raw_str} (пример: 128k, 192k)",
                    )
            elif sub_k in ("mediadialog.default.scale", "mediadialog.default.poster_scale") and raw_str:
                if not re.match(r"^(?:original|none|2160p|4k|1440p|2k|1080p|fhd|720p|hd|480p|sd|360p|\d{3,4}p|\d{2,4}x\d{2,4})$", raw_str.strip().lower()):
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                        f"Недопустимое разрешение '{sub_k}': {raw_str}",
                    )

            await mngr.set(full_k, serialized, is_secret=False)
        updated_fields.append("settings")

    await audit(
        session,
        action="branding.update",
        actor_id=acc.id,
        actor_role=acc.role.name if acc.role else None,
        target_type="ui",
        target_id=scope,
        ip=request.client.host if request.client else None,
        meta={"fields": updated_fields},
    )
    await session.commit()

    raw = await mngr.get_group(f"ui.{scope}.")
    out = _build_body(scope, raw)
    out["currency"] = (await mngr.get("billing.currency")) or DEFAULT_CURRENCY
    return out


__all__ = ["router"]
