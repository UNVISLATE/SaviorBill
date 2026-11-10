"""Админ: платежи и платёжные провайдеры (/api/v1/admin/purchases)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.media import get_media_mngr
from dependencies.oauth import get_secbox
from dependencies.payment import PayMngr, get_pay_mngr
from dependencies.rbac import require_perm
from enums import PayStatus
from models.payment_providers import PaymentProvidersModel
from models.system_media import SystemMediaMngr
from models.user_payments import UserPaymentsModel
from schemas.payment_provider import PayProviderCreate, PayProvider, PayProviderPatch
from schemas.payments import PaymentAdmin
from schemas.page import Page
from utils.pagination import (
    PageParams,
    apply_sort,
    page_params,
    paginate_search,
    q_param,
    sort_param,
)
from security.sec.box import SecBox

router = APIRouter()

_PAYMENT_SORT_FIELDS = {
    "id",
    "amount",
    "status",
    "provider",
    "created_at",
    "paid_at",
    "currency",
}


# --- платежи -------------------------------------------------------------
@router.get(
    "",
    response_model=Page[PaymentAdmin],
    dependencies=[Depends(require_perm("purchases.read"))],
    summary="Payments",
    description="`q` searches provider/external_id (exact substring, no "
    f"fuzzy — identifiers aren't meant to be 'similar'-matched); `sort` "
    f"accepts {'/'.join(sorted(_PAYMENT_SORT_FIELDS))}.",
)
async def list_payments(
    pp: PageParams = Depends(page_params),
    q: str | None = Depends(q_param),
    sort: str | None = Depends(sort_param),
    session: AsyncSession = Depends(get_db_session),
) -> Page[PaymentAdmin]:
    stmt = apply_sort(select(UserPaymentsModel), UserPaymentsModel, sort, _PAYMENT_SORT_FIELDS)
    if sort is None:
        stmt = stmt.order_by(UserPaymentsModel.id.desc())
    items, total, has_more = await paginate_search(
        session,
        stmt,
        UserPaymentsModel,
        PaymentAdmin.from_model,
        limit=pp.limit,
        offset=pp.offset,
        q=q,
        search_fields=("provider", "external_id"),
    )
    return Page(
        items=items, total=total, limit=pp.limit, offset=pp.offset, has_more=has_more
    )


@router.get(
    "/providers",
    response_model=list[PayProvider],
    dependencies=[Depends(require_perm("purchases.providers.read"))],
    summary="Payment providers",
)
async def list_providers(
    session: AsyncSession = Depends(get_db_session),
) -> list[PayProvider]:
    rows = await session.scalars(
        select(PaymentProvidersModel).order_by(PaymentProvidersModel.id)
    )
    return [PayProvider.from_model(r) for r in rows]


async def _require_media(mngr: SystemMediaMngr, media_id: int) -> None:
    """Проверить, что медиа для иконки провайдера существует."""
    if await mngr.by_id(media_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "media not found")


# --- провайдеры ----------------------------------------------------------
@router.post(
    "/providers",
    response_model=PayProvider,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("purchases.providers.create"))],
    summary="Create payment provider",
    description="Create a payment provider with encrypted secrets.",
)
async def create_provider(
    body: PayProviderCreate,
    session: AsyncSession = Depends(get_db_session),
    box: SecBox = Depends(get_secbox),
    media: SystemMediaMngr = Depends(get_media_mngr),
) -> PayProvider:
    if await session.scalar(
        select(PaymentProvidersModel).where(PaymentProvidersModel.slug == body.slug)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "provider slug already exists")
    if body.icon_media_id is not None:
        await _require_media(media, body.icon_media_id)
    prov = PaymentProvidersModel(
        slug=body.slug,
        title=body.title,
        enabled=body.enabled,
        is_recommended=body.is_recommended,
        currency=body.currency,
        currencies=body.currencies,
        fee_enabled=body.fee_enabled,
        fee_percent=body.fee_percent,
        add_fee_to_amount=body.add_fee_to_amount,
        secrets_enc=box.seal(json.dumps(body.secrets)),
        script_id=body.script_id,
        script_version=body.script_version,
        icon_media_id=body.icon_media_id,
        extra=body.extra,
    )
    session.add(prov)
    await session.commit()
    await session.refresh(prov, attribute_names=["icon"])
    return PayProvider.from_model(prov)


@router.patch(
    "/providers/{provider_id}",
    response_model=PayProvider,
    dependencies=[Depends(require_perm("purchases.providers.edit"))],
    summary="Update payment provider",
    description="Update a payment provider.",
)
async def update_provider(
    provider_id: int,
    body: PayProviderPatch,
    session: AsyncSession = Depends(get_db_session),
    box: SecBox = Depends(get_secbox),
    media: SystemMediaMngr = Depends(get_media_mngr),
) -> PayProvider:
    prov = await session.get(PaymentProvidersModel, provider_id)
    if prov is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "provider not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("icon_media_id") is not None:
        await _require_media(media, data["icon_media_id"])
    if "secrets" in data:
        prov.secrets_enc = box.seal(json.dumps(data.pop("secrets")))
    for field, value in data.items():
        setattr(prov, field, value)
    await session.commit()
    await session.refresh(prov, attribute_names=["icon"])
    return PayProvider.from_model(prov)


# Карточка платежа объявлена после /purchases/providers, чтобы "providers"
# не перехватывался как {payment_id}.
@router.get(
    "/{payment_id}",
    response_model=PaymentAdmin,
    dependencies=[Depends(require_perm("purchases.read"))],
    summary="Payment details",
)
async def get_payment(
    payment_id: int, session: AsyncSession = Depends(get_db_session)
) -> PaymentAdmin:
    pay = await session.get(UserPaymentsModel, payment_id)
    if pay is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "payment not found")
    return PaymentAdmin.from_model(pay)


@router.post(
    "/{payment_id}/recheck",
    response_model=PaymentAdmin,
    dependencies=[Depends(require_perm("purchases.recheck"))],
    summary="Recheck payment",
    description="Request a payment status refresh from the provider.",
)
async def recheck_payment(
    payment_id: int,
    session: AsyncSession = Depends(get_db_session),
    svc: PayMngr = Depends(get_pay_mngr),
) -> PaymentAdmin:
    pay = await session.get(UserPaymentsModel, payment_id)
    if pay is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "payment not found")
    # Ручной recheck сбрасывает "тупиковый" wait обратно в pending для сверки.
    if pay.status == PayStatus.WAIT:
        pay.status = PayStatus.PENDING
    pay = await svc.recheck(pay)
    await session.commit()
    return PaymentAdmin.from_model(pay)


@router.post(
    "/{payment_id}/refund",
    response_model=PaymentAdmin,
    dependencies=[Depends(require_perm("purchases.refund"))],
    summary="Refund payment",
    description="Request a refund for a paid payment.",
)
async def refund_payment(
    payment_id: int,
    session: AsyncSession = Depends(get_db_session),
    svc: PayMngr = Depends(get_pay_mngr),
) -> PaymentAdmin:
    pay = await session.get(UserPaymentsModel, payment_id)
    if pay is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "payment not found")
    pay = await svc.refund(pay)
    await session.commit()
    return PaymentAdmin.from_model(pay)


__all__ = ["router"]
