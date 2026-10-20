"""Внутренний API управления ключами для LuaWorker."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from core.config import AppConfig
from dependencies.catalog import ServiceKeysMngr, get_servicekeys_mngr
from enums import Delivery
from models.service import ServiceModel
from models.service_keys import ServiceKeysModel

router = APIRouter(prefix="/service-keys")


async def require_lua_token(
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    cfg: AppConfig = request.app.state.settings
    expected = cfg.LUA_SERVICE_TOKEN
    if not expected:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "LUA_SERVICE_TOKEN не настроен на сервере"
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Требуется заголовок Authorization: Bearer <token>"
        )
    token = authorization[7:].strip()
    if token != expected:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Неверный сервисный токен")


class LuaKeysImportIn(BaseModel):
    service: str | int = Field(description="ID услуги или её slug")
    keys: list[str] = Field(min_length=1, description="Список ключей для импорта")


class LuaKeysImportOut(BaseModel):
    ok: bool
    imported: int
    duplicates: int
    available_total: int


@router.post(
    "/import",
    response_model=LuaKeysImportOut,
    dependencies=[Depends(require_lua_token)],
    summary="Внутренний импорт ключей из Lua-скрипта",
)
async def import_keys_internal(
    body: LuaKeysImportIn,
    mngr: ServiceKeysMngr = Depends(get_servicekeys_mngr),
) -> LuaKeysImportOut:
    target = body.service
    service: ServiceModel | None = None
    if isinstance(target, int) or (isinstance(target, str) and target.isdigit()):
        service = await mngr.s.get(ServiceModel, int(target))
    else:
        service = await mngr.s.scalar(
            select(ServiceModel).where(ServiceModel.slug == str(target))
        )

    if service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Услуга '{target}' не найдена")

    if service.delivery != Delivery.KEY:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Услуга '{service.name}' имеет способ выдачи '{service.delivery}', а не цифровой ключ",
        )

    created, skipped = await mngr.bulk_create(service.id, body.keys)
    await mngr.s.commit()

    avail = await mngr.s.scalar(
        select(func.count(ServiceKeysModel.id)).where(
            ServiceKeysModel.service_id == service.id,
            ServiceKeysModel.is_used.is_(False),
        )
    )

    return LuaKeysImportOut(
        ok=True,
        imported=len(created),
        duplicates=skipped,
        available_total=int(avail or 0),
    )


__all__ = ["router"]
