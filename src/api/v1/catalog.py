"""Публичный каталог: услуги и дерево каталогов."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from dependencies.catalog import (
    ServiceCatalogsMngr,
    ServiceKeysMngr,
    ServiceMngr,
    get_catalog_mngr,
    get_service_mngr,
    get_servicekeys_mngr,
)
from dependencies.auth import get_current_acc_optional
from dependencies.promo import PromoCodesMngr, get_promo_mngr
from dependencies.ratelimit import LimitKind, authenticated_ident, enforce_rate_limit
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.valkey import get_valkey_client
import valkey.asyncio as valkey
from enums import Delivery
from models.user import UserModel
from schemas.catalog import CatalogResponse
from schemas.page import Page
from schemas.promo import PromoQuote
from schemas.service import Service
from services.catalog_cache import (
    get_cached_catalogs,
    get_cached_services,
    set_cached_catalogs,
    set_cached_services,
)
from utils.pagination import PageParams, page_params, paginate
from utils.public_pagination import normalize_public_limit

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])


async def _with_stock(
    svc: Service, service_id: int, keys_mngr: ServiceKeysMngr
) -> Service:
    """Проставить ``out_of_stock`` для delivery=key (вычисляемый статус, §4.2)."""
    if svc.delivery != Delivery.KEY:
        return svc
    available = await keys_mngr.count_available(service_id)
    return svc.with_stock(available == 0)


@router.get("/catalogs", response_model=list[CatalogResponse], summary="Catalog tree")
async def list_catalogs(
    mngr: ServiceCatalogsMngr = Depends(get_catalog_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> list[CatalogResponse]:
    """Все активные каталоги (плоско; иерархия — через parent_id). Кешируется в Valkey."""
    cached = await get_cached_catalogs(vk)
    if cached is not None:
        return [CatalogResponse.model_validate(c) for c in cached]

    rows = await mngr.list_all()
    result = [CatalogResponse.from_model(c) for c in rows if c.is_active]

    ttl_raw = await settings.get("cache.catalog.ttl_sec", "180")
    ttl = int(ttl_raw) if ttl_raw and ttl_raw.isdigit() else 180
    await set_cached_catalogs(vk, [c.model_dump() for c in result], ttl_sec=ttl)
    return result


@router.get("/services", response_model=Page[Service], summary="Services")
async def list_services(
    catalog_id: int | None = Query(default=None, description="filter by catalog"),
    pp: PageParams = Depends(page_params),
    acc: UserModel | None = Depends(get_current_acc_optional),
    vk: valkey.Valkey = Depends(get_valkey_client),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    mngr: ServiceMngr = Depends(get_service_mngr),
    keys_mngr: ServiceKeysMngr = Depends(get_servicekeys_mngr),
) -> Page[Service]:
    """Активные услуги каталога (опц. в рамках одного каталога), постранично."""
    effective_limit = pp.limit

    # Для неавторизованных клиентов квантуем limit и проверяем кэш
    if acc is None:
        max_limit_raw = await settings.get("catalog.public.limit_max", "50")
        step_raw = await settings.get("catalog.public.limit_step", "10")
        max_limit = int(max_limit_raw) if max_limit_raw and max_limit_raw.isdigit() else 50
        step = int(step_raw) if step_raw and step_raw.isdigit() else 10
        effective_limit = normalize_public_limit(pp.limit, max_limit=max_limit, step=step)

        cached = await get_cached_services(vk, catalog_id, effective_limit, pp.offset)
        if cached is not None:
            return Page[Service].model_validate(cached)

    items, total, has_more = await paginate(
        mngr.s,
        mngr.stmt_active(catalog_id),
        Service.from_model,
        limit=effective_limit,
        offset=pp.offset,
    )
    items = [await _with_stock(svc, svc.id, keys_mngr) for svc in items]
    page_res = Page(
        items=items, total=total, limit=effective_limit, offset=pp.offset, has_more=has_more
    )

    if acc is None:
        ttl_raw = await settings.get("cache.catalog.ttl_sec", "180")
        ttl = int(ttl_raw) if ttl_raw and ttl_raw.isdigit() else 180
        await set_cached_services(
            vk, catalog_id, effective_limit, pp.offset, page_res.model_dump(), ttl_sec=ttl
        )

    return page_res


@router.get("/services/{service_id}", response_model=Service, summary="Service details")
async def get_service(
    request: Request,
    response: Response,
    service_id: int,
    promo: str | None = Query(
        default=None, description="Preview discount for this promo code"
    ),
    acc: UserModel | None = Depends(get_current_acc_optional),
    mngr: ServiceMngr = Depends(get_service_mngr),
    keys_mngr: ServiceKeysMngr = Depends(get_servicekeys_mngr),
    promo_mngr: PromoCodesMngr = Depends(get_promo_mngr),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> Service:
    """Получить активную услугу по идентификатору.

    ``?promo=CODE`` — превью скидки без побочных эффектов (см.
    ``PromoCodesMngr.quote_for``); альтернатива отдельному
    ``GET /promocodes/{code}/quote``. Требует авторизации и лимитируется
    отдельно — анонимный перебор кодов через этот путь исключён так же, как
    и через основной эндпоинт (см. AUDIT.md §2.3).
    """
    svc = await mngr.get_active(service_id)
    result = await _with_stock(Service.from_model(svc), service_id, keys_mngr)
    if promo:
        if acc is None:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "authentication required to preview promo code",
            )
        await enforce_rate_limit(
            request,
            response,
            settings,
            authenticated_ident(acc),
            "catalog.promo_quote",
            LimitKind.SENSITIVE,
        )
        valid, discount, reason = await promo_mngr.quote_for(promo, svc, acc)
        result = result.with_promo_quote(
            PromoQuote(
                valid=valid,
                code=promo,
                service_id=service_id,
                price=svc.price,
                discount=discount,
                final_price=svc.price - discount,
                reason=reason,
            )
        )
    return result


__all__ = ["router"]
