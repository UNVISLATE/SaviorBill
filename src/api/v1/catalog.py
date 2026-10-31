"""Публичный каталог: услуги и дерево каталогов."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from models.service import ServiceModel

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
    get_cached_catalog_ids,
    get_cached_service_entities,
    set_cached_catalogs,
    set_cached_catalog_ids,
    set_cached_service_entities,
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
    step_raw = await settings.get("catalog.public.limit_step", "10")
    step = int(step_raw) if step_raw and step_raw.isdigit() else 10

    if acc is None:
        guest_raw = await settings.get(
            "catalog.limit_max_guest",
            await settings.get("catalog.public.limit_max", "20"),
        )
        max_limit = int(guest_raw) if guest_raw and guest_raw.isdigit() else 20
    else:
        auth_raw = await settings.get("catalog.limit_max_auth", "100")
        max_limit = int(auth_raw) if auth_raw and auth_raw.isdigit() else 100

    effective_limit = normalize_public_limit(pp.limit, max_limit=max_limit, step=step)

    ttl_raw = await settings.get("cache.catalog.ttl_sec", "180")
    ttl = int(ttl_raw) if ttl_raw and ttl_raw.isdigit() else 180

    # 1. Уровень 1: Индекс ID активных услуг каталога (Valkey)
    ids = await get_cached_catalog_ids(vk, catalog_id)
    if ids is None:
        stmt = select(ServiceModel.id).where(ServiceModel.is_active.is_(True))
        if catalog_id is not None:
            stmt = stmt.where(ServiceModel.catalog_id == catalog_id)
        stmt = stmt.order_by(ServiceModel.id)
        rows = await mngr.s.scalars(stmt)
        ids = list(rows)
        await set_cached_catalog_ids(vk, catalog_id, ids, ttl_sec=ttl)

    total = len(ids)
    slice_ids = ids[pp.offset : pp.offset + effective_limit]
    has_more = (pp.offset + effective_limit) < total

    if not slice_ids:
        return Page(
            items=[], total=total, limit=effective_limit, offset=pp.offset, has_more=False
        )

    # 2. Уровень 2: Пакетный MGET сущностей из Valkey
    cached_entities, missing_ids = await get_cached_service_entities(vk, slice_ids)

    # 3. Если каких-то карточек ещё нет в кэше — догружаем только их
    if missing_ids:
        stmt_missing = select(ServiceModel).where(ServiceModel.id.in_(missing_ids))
        missing_models_rows = await mngr.s.scalars(stmt_missing)
        missing_models = {m.id: m for m in missing_models_rows}
        missing_to_cache: dict[int, dict[str, Any]] = {}

        for mid in missing_ids:
            model = missing_models.get(mid)
            if model is not None:
                svc = Service.from_model(model)
                svc = await _with_stock(svc, svc.id, keys_mngr)
                dump = svc.model_dump()
                cached_entities[mid] = dump
                missing_to_cache[mid] = dump

        if missing_to_cache:
            await set_cached_service_entities(vk, missing_to_cache, ttl_sec=ttl)

    # Сборка готовой страницы в точном порядке среза slice_ids
    items: list[Service] = []
    for sid in slice_ids:
        raw_entity = cached_entities.get(sid)
        if raw_entity is not None:
            items.append(Service.model_validate(raw_entity))

    return Page(
        items=items, total=total, limit=effective_limit, offset=pp.offset, has_more=has_more
    )


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
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> Service:
    """Получить активную услугу по идентификатору.

    ``?promo=CODE`` — превью скидки без побочных эффектов (см.
    ``PromoCodesMngr.quote_for``); альтернатива отдельному
    ``GET /promocodes/{code}/quote``. Требует авторизации и лимитируется
    отдельно — анонимный перебор кодов через этот путь исключён так же, как
    и через основной эндпоинт (см. AUDIT.md §2.3).
    """
    ttl_raw = await settings.get("cache.catalog.ttl_sec", "180")
    ttl = int(ttl_raw) if ttl_raw and ttl_raw.isdigit() else 180

    if not promo:
        entities, missing = await get_cached_service_entities(vk, [service_id])
        if service_id in entities:
            return Service.model_validate(entities[service_id])

    svc = await mngr.get_active(service_id)
    result = await _with_stock(Service.from_model(svc), service_id, keys_mngr)
    await set_cached_service_entities(vk, {service_id: result.model_dump()}, ttl_sec=ttl)
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
