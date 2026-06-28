"""Админ: платежи и платёжные провайдеры (/api/v1/admin/purchases)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.oauth import get_secbox
from dependencies.rbac import require_perm
from models.pay_provider import PayProvider
from models.payment import Payment
from schemas.admin import PayProviderIn, PayProviderOut, PayProviderPatch
from schemas.payments import PaymentAdminOut
from utils.sec.box import SecBox

router = APIRouter()


# --- платежи -------------------------------------------------------------
@router.get(
    "/purchases",
    response_model=list[PaymentAdminOut],
    dependencies=[Depends(require_perm("purchases.read"))],
    summary="Список платежей",
)
async def list_payments(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> list[Payment]:
    rows = await session.scalars(
        select(Payment).order_by(Payment.id.desc()).limit(limit).offset(offset)
    )
    return list(rows)


@router.get(
    "/purchases/providers",
    response_model=list[PayProviderOut],
    dependencies=[Depends(require_perm("purchases.providers"))],
    summary="Список платёжных провайдеров",
)
async def list_providers(
    session: AsyncSession = Depends(get_db_session),
) -> list[PayProvider]:
    rows = await session.scalars(select(PayProvider).order_by(PayProvider.id))
    return list(rows)


# --- провайдеры ----------------------------------------------------------
@router.post(
    "/purchases/providers",
    response_model=PayProviderOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("purchases.providers"))],
    summary="Создать платёжного провайдера",
)
async def create_provider(
    body: PayProviderIn,
    session: AsyncSession = Depends(get_db_session),
    box: SecBox = Depends(get_secbox),
) -> PayProvider:
    if await session.scalar(select(PayProvider).where(PayProvider.slug == body.slug)):
        raise HTTPException(status.HTTP_409_CONFLICT, "slug провайдера занят")
    prov = PayProvider(
        slug=body.slug,
        title=body.title,
        enabled=body.enabled,
        currency=body.currency,
        secrets_enc=box.seal(json.dumps(body.secrets)),
        init_script_id=body.init_script_id,
        cb_script_id=body.cb_script_id,
        extra=body.extra,
    )
    session.add(prov)
    await session.commit()
    return prov


@router.patch(
    "/purchases/providers/{provider_id}",
    response_model=PayProviderOut,
    dependencies=[Depends(require_perm("purchases.providers"))],
    summary="Изменить платёжного провайдера",
)
async def update_provider(
    provider_id: int,
    body: PayProviderPatch,
    session: AsyncSession = Depends(get_db_session),
    box: SecBox = Depends(get_secbox),
) -> PayProvider:
    prov = await session.get(PayProvider, provider_id)
    if prov is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "провайдер не найден")
    data = body.model_dump(exclude_unset=True)
    if "secrets" in data:
        prov.secrets_enc = box.seal(json.dumps(data.pop("secrets")))
    for field, value in data.items():
        setattr(prov, field, value)
    await session.commit()
    return prov


# Карточка платежа объявлена после /purchases/providers, чтобы "providers"
# не перехватывался как {payment_id}.
@router.get(
    "/purchases/{payment_id}",
    response_model=PaymentAdminOut,
    dependencies=[Depends(require_perm("purchases.read"))],
    summary="Карточка платежа",
)
async def get_payment(
    payment_id: int, session: AsyncSession = Depends(get_db_session)
) -> Payment:
    pay = await session.get(Payment, payment_id)
    if pay is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "платёж не найден")
    return pay


__all__ = ["router"]
