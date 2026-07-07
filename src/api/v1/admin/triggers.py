"""Админ: управление триггерами (/api/v1/admin/triggers)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from dependencies.rbac import require_perm
from dependencies.triggers import get_trigger_mngr
from integrations.triggers import ACTION_KEYS, ALL_EVENTS
from models.triggers import TriggerMngr
from schemas.trigger import Trigger, TriggerCreate, TriggerMeta, TriggerPatch
from utils.apidoc import with_fields

router = APIRouter()


@router.get(
    "/triggers/meta",
    response_model=TriggerMeta,
    dependencies=[Depends(require_perm("triggers.read"))],
    summary="Справочник событий и действий",
    description="Доступные доменные события и ключи действий для UI.",
)
async def triggers_meta() -> TriggerMeta:
    return TriggerMeta(events=list(ALL_EVENTS), actions=list(ACTION_KEYS))


@router.get(
    "/triggers",
    response_model=list[Trigger],
    dependencies=[Depends(require_perm("triggers.read"))],
    summary="Список триггеров",
)
async def list_triggers(
    mngr: TriggerMngr = Depends(get_trigger_mngr),
) -> list[Trigger]:
    rows = await mngr.list_all()
    return [Trigger.from_model(r) for r in rows]


@router.post(
    "/triggers",
    response_model=Trigger,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("triggers.create"))],
    summary="Создать триггер",
    description=with_fields(
        "Связывает доменное событие с действием (email/lua) и условием.",
        TriggerCreate,
    ),
)
async def create_trigger(
    body: TriggerCreate,
    mngr: TriggerMngr = Depends(get_trigger_mngr),
) -> Trigger:
    row = await mngr.create(body.model_dump())
    await mngr.s.commit()
    return Trigger.from_model(row)


@router.patch(
    "/triggers/{trig_id}",
    response_model=Trigger,
    dependencies=[Depends(require_perm("triggers.edit"))],
    summary="Изменить триггер",
    description=with_fields(
        "Частично обновляет триггер — передаются только изменяемые поля.",
        TriggerPatch,
    ),
)
async def patch_trigger(
    trig_id: int,
    body: TriggerPatch,
    mngr: TriggerMngr = Depends(get_trigger_mngr),
) -> Trigger:
    row = await mngr.patch(trig_id, body.model_dump(exclude_unset=True))
    await mngr.s.commit()
    return Trigger.from_model(row)


@router.delete(
    "/triggers/{trig_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("triggers.delete"))],
    summary="Удалить триггер",
)
async def delete_trigger(
    trig_id: int,
    mngr: TriggerMngr = Depends(get_trigger_mngr),
) -> None:
    await mngr.delete(trig_id)
    await mngr.s.commit()


__all__ = ["router"]
