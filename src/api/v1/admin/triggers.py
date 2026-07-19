"""Админ: управление триггерами (/api/v1/admin/triggers)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from dependencies.rbac import require_perm
from dependencies.triggers import get_trigger_mngr
from lifecycle.triggers import ACTION_KEYS, ALL_EVENTS
from models.triggers import TriggerMngr
from schemas.trigger import Trigger, TriggerCreate, TriggerMeta, TriggerPatch

router = APIRouter()


@router.get(
    "/meta",
    response_model=TriggerMeta,
    dependencies=[Depends(require_perm("triggers.read"))],
    summary="Trigger metadata",
    description="Available events and action keys.",
)
async def triggers_meta() -> TriggerMeta:
    return TriggerMeta(events=list(ALL_EVENTS), actions=list(ACTION_KEYS))


@router.get(
    "",
    response_model=list[Trigger],
    dependencies=[Depends(require_perm("triggers.read"))],
    summary="Triggers",
)
async def list_triggers(
    mngr: TriggerMngr = Depends(get_trigger_mngr),
) -> list[Trigger]:
    rows = await mngr.list_all()
    return [Trigger.from_model(r) for r in rows]


@router.get(
    "/{trig_id}",
    response_model=Trigger,
    dependencies=[Depends(require_perm("triggers.read"))],
    summary="Get trigger",
)
async def get_trigger(
    trig_id: int,
    mngr: TriggerMngr = Depends(get_trigger_mngr),
) -> Trigger:
    row = await mngr.by_id(trig_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "trigger not found")
    return Trigger.from_model(row)


@router.post(
    "",
    response_model=Trigger,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("triggers.create"))],
    summary="Create trigger",
    description="Create a trigger.",
)
async def create_trigger(
    body: TriggerCreate,
    mngr: TriggerMngr = Depends(get_trigger_mngr),
) -> Trigger:
    row = await mngr.create(body.model_dump())
    await mngr.s.commit()
    return Trigger.from_model(row)


@router.patch(
    "/{trig_id}",
    response_model=Trigger,
    dependencies=[Depends(require_perm("triggers.edit"))],
    summary="Update trigger",
    description="Update a trigger.",
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
    "/{trig_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("triggers.delete"))],
    summary="Delete trigger",
)
async def delete_trigger(
    trig_id: int,
    mngr: TriggerMngr = Depends(get_trigger_mngr),
) -> None:
    await mngr.delete(trig_id)
    await mngr.s.commit()


__all__ = ["router"]
