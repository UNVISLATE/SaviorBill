"""Админ: платежи и платёжные провайдеры (/api/v1/admin/purchases)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.oauth import get_secbox
from dependencies.payment import PayMngr, get_pay_mngr
from dependencies.rbac import require_perm
from enums import PayStatus
from models.payment_providers import PaymentProvidersModel
from models.user_payments import UserPaymentsModel
from schemas.payment_provider import PayProviderCreate, PayProvider, PayProviderPatch
from schemas.payments import PaymentAdmin
from schemas.page import Page
from utils.pagination import paginate
from utils.sec.box import SecBox

router = APIRouter()


# --- платежи -------------------------------------------------------------
@router.get(
    "/purchases",
    response_model=Page[PaymentAdmin],
    dependencies=[Depends(require_perm("purchases.read"))],
    summary="Список платежей",
)
async def list_payments(
    limit: int = Query(50, ge=1, le=200, description="Размер страницы (опционально)"),
    offset: int = Query(0, ge=0, description="Смещение выборки (опционально)"),
    session: AsyncSession = Depends(get_db_session),
) -> Page[PaymentAdmin]:
    stmt = select(UserPaymentsModel).order_by(UserPaymentsModel.id.desc())
    items, total = await paginate(
        session, stmt, PaymentAdmin.from_model, limit=limit, offset=offset
    )
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/purchases/providers",
    response_model=list[PayProvider],
    dependencies=[Depends(require_perm("purchases.providers"))],
    summary="Список платёжных провайдеров",
)
async def list_providers(
    session: AsyncSession = Depends(get_db_session),
) -> list[PayProvider]:
    rows = await session.scalars(
        select(PaymentProvidersModel).order_by(PaymentProvidersModel.id)
    )
    return [PayProvider.from_model(r) for r in rows]


# --- провайдеры ----------------------------------------------------------
@router.post(
    "/purchases/providers",
    response_model=PayProvider,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("purchases.providers"))],
    summary="Создать платёжного провайдера",
)
async def create_provider(
    body: PayProviderCreate,
    session: AsyncSession = Depends(get_db_session),
    box: SecBox = Depends(get_secbox),
) -> PayProvider:
    if await session.scalar(
        select(PaymentProvidersModel).where(PaymentProvidersModel.slug == body.slug)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "slug провайдера занят")
    prov = PaymentProvidersModel(
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
    return PayProvider.from_model(prov)


@router.patch(
    "/purchases/providers/{provider_id}",
    response_model=PayProvider,
    dependencies=[Depends(require_perm("purchases.providers"))],
    summary="Изменить платёжного провайдера",
)
async def update_provider(
    provider_id: int,
    body: PayProviderPatch,
    session: AsyncSession = Depends(get_db_session),
    box: SecBox = Depends(get_secbox),
) -> PayProvider:
    prov = await session.get(PaymentProvidersModel, provider_id)
    if prov is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "провайдер не найден")
    data = body.model_dump(exclude_unset=True)
    if "secrets" in data:
        prov.secrets_enc = box.seal(json.dumps(data.pop("secrets")))
    for field, value in data.items():
        setattr(prov, field, value)
    await session.commit()
    return PayProvider.from_model(prov)


# Карточка платежа объявлена после /purchases/providers, чтобы "providers"
# не перехватывался как {payment_id}.
@router.get(
    "/purchases/{payment_id}",
    response_model=PaymentAdmin,
    dependencies=[Depends(require_perm("purchases.read"))],
    summary="Карточка платежа",
)
async def get_payment(
    payment_id: int, session: AsyncSession = Depends(get_db_session)
) -> PaymentAdmin:
    pay = await session.get(UserPaymentsModel, payment_id)
    if pay is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "платёж не найден")
    return PaymentAdmin.from_model(pay)


@router.post(
    "/purchases/{payment_id}/recheck",
    response_model=PaymentAdmin,
    dependencies=[Depends(require_perm("purchases.recheck"))],
    summary="Ручная перепроверка платежа",
    description=(
        "Инициировать сверку статуса платежа с провайдером (директива recheck). "
        "Применимо к платежам в статусах pending/wait; callback-скрипт обращается "
        "к API провайдера и обновляет статус. Идемпотентно для paid/failed."
    ),
)
async def recheck_payment(
    payment_id: int,
    session: AsyncSession = Depends(get_db_session),
    svc: PayMngr = Depends(get_pay_mngr),
) -> PaymentAdmin:
    pay = await session.get(UserPaymentsModel, payment_id)
    if pay is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "платёж не найден")
    # Ручной recheck сбрасывает "тупиковый" wait обратно в pending для сверки.
    if pay.status == PayStatus.WAIT:
        pay.status = PayStatus.PENDING
    pay = await svc.recheck(pay)
    await session.commit()
    return PaymentAdmin.from_model(pay)


__all__ = ["router"]
