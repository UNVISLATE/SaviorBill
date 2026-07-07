"""Админ: ручное (raw) управление таблицей ``settings`` (/api/v1/admin/settings/raw).

Позволяет напрямую просматривать/создавать/менять/удалять произвольные строки
таблицы ``settings`` (key-value). Зашифрованные системные значения (``is_secret``)
показываются без содержимого (``value: null``) и недоступны для редактирования
или удаления через этот роутер — ими управляют профильные разделы админки
(email/SMTP и т.п.), где значение шифруется осознанно через каталог настроек.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from models.system_settings import SystemSettingsModel
from models.user import UserModel
from schemas.page import Page
from schemas.settings_raw import SettingRawOut, SettingRawUpsert
from services.audit import audit
from utils.apidoc import with_fields
from utils.pagination import PageParams, page_params, paginate
from utils.settings_def import by_key

router = APIRouter()


def _is_locked(row: SystemSettingsModel | None, key: str) -> bool:
    """Заблокирован ли ключ для raw-редактирования (уже зашифрован в БД либо
    зарегистрирован в каталоге настроек как секретный)."""
    if row is not None and row.is_secret:
        return True
    spec = by_key(key)
    return bool(spec and spec.secret)


@router.get(
    "/settings/raw",
    response_model=Page[SettingRawOut],
    dependencies=[Depends(require_perm("settings.raw.read"))],
    summary="Все строки таблицы settings (raw)",
    description=(
        "Постраничный список настроек как есть в БД. Значения зашифрованных "
        "(`is_secret=true`) записей не раскрываются (`value: null`, "
        "`editable: false`)."
    ),
)
async def list_settings_raw(
    pp: PageParams = Depends(page_params),
    session: AsyncSession = Depends(get_db_session),
) -> Page[SettingRawOut]:
    stmt = select(SystemSettingsModel).order_by(SystemSettingsModel.key)
    items, total, has_more = await paginate(
        session,
        stmt,
        lambda r: SettingRawOut.from_model(r, by_key(r.key)),
        limit=pp.limit,
        offset=pp.offset,
    )
    return Page(
        items=items, total=total, limit=pp.limit, offset=pp.offset, has_more=has_more
    )


@router.get(
    "/settings/raw/{key}",
    response_model=SettingRawOut,
    dependencies=[Depends(require_perm("settings.raw.read"))],
    summary="Одна строка таблицы settings (raw)",
)
async def get_setting_raw(
    key: str,
    session: AsyncSession = Depends(get_db_session),
) -> SettingRawOut:
    row = await session.get(SystemSettingsModel, key)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "настройка не найдена")
    return SettingRawOut.from_model(row, by_key(key))


@router.put(
    "/settings/raw/{key}",
    response_model=SettingRawOut,
    summary="Создать/изменить значение настройки (raw)",
    description=with_fields(
        "Создаёт запись, если ключа ещё нет, либо обновляет значение "
        "существующей. Запрещено для зашифрованных системных ключей "
        "(`is_secret=true` в БД или в каталоге настроек) — вернёт 403.",
        SettingRawUpsert,
    ),
)
async def upsert_setting_raw(
    request: Request,
    key: str,
    body: SettingRawUpsert,
    session: AsyncSession = Depends(get_db_session),
    mngr: SystemSettingsMngr = Depends(get_settings_mngr),
    acc: UserModel = Depends(require_perm("settings.raw.edit")),
) -> SettingRawOut:
    existing = await session.get(SystemSettingsModel, key)
    if _is_locked(existing, key):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "зашифрованную системную настройку нельзя менять через raw-редактор",
        )
    await mngr.set(key, body.value, is_secret=False)
    await audit(
        session,
        action="settings.raw.set",
        actor_id=acc.id,
        actor_role=acc.role.name if acc.role else None,
        target_type="setting",
        target_id=key,
        ip=request.client.host if request.client else None,
        meta={"created": existing is None},
    )
    await session.commit()
    row = await session.get(SystemSettingsModel, key)
    assert row is not None
    return SettingRawOut.from_model(row, by_key(key))


@router.delete(
    "/settings/raw/{key}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить значение (raw)",
    description=(
        "Удаляет строку из таблицы settings. Запрещено для зашифрованных "
        "системных ключей — вернёт 403."
    ),
)
async def delete_setting_raw(
    request: Request,
    key: str,
    session: AsyncSession = Depends(get_db_session),
    mngr: SystemSettingsMngr = Depends(get_settings_mngr),
    acc: UserModel = Depends(require_perm("settings.raw.delete")),
) -> None:
    row = await session.get(SystemSettingsModel, key)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "настройка не найдена")
    if _is_locked(row, key):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "зашифрованную системную настройку нельзя удалить через raw-редактор",
        )
    await session.delete(row)
    await mngr.invalidate(key)
    await audit(
        session,
        action="settings.raw.delete",
        actor_id=acc.id,
        actor_role=acc.role.name if acc.role else None,
        target_type="setting",
        target_id=key,
        ip=request.client.host if request.client else None,
    )
    await session.commit()


__all__ = ["router"]
