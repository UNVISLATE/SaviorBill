"""Публичные эндпоинты для магазина и гостевого чекаута (/api/v1/public/*)."""

from __future__ import annotations

import secrets
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import AppConfig
from dependencies.catalog import ServiceMngr, get_service_mngr
from dependencies.db import get_db_session
from dependencies.guest_checkout import GuestCheckoutSvc, get_guest_checkout_svc
from dependencies.payment import PayMngr, PaymentProvidersMngr, get_pay_mngr, get_pay_providers_mngr
from dependencies.promo import PromoCodesMngr, get_promo_mngr
from dependencies.ratelimit import LimitKind, rate_limit
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.triggers import get_dispatcher
from dependencies.usersvc import UserServicesMngr, get_usersvc_mngr
from enums import BaseRole, PayTarget, PromoKind
from lifecycle.triggers import TriggerDispatcher, TriggerEvent
from models.banned_email_domains import BannedEmailDomainsMngr
from models.user import UserModel, UserMngr
from models.user_payments import UserPaymentsModel
from schemas.guest import GuestPurchaseCreate, GuestPurchaseResult, PublicOrderView
from schemas.payment_provider import PayProviderPublic
from schemas.types import normalize_email
from services.guest_checkout import mask_email
from services.pricing import resolve_service_order
from utils.urls import is_safe_return_url

router = APIRouter(prefix="/api/v1/public", tags=["public"])


@router.get(
    "/purchases/providers",
    response_model=list[PayProviderPublic],
    summary="Public payment providers for checkout",
    description="Lists enabled payment providers available for guest and storefront checkout.",
    dependencies=[Depends(rate_limit("public.providers", LimitKind.DEFAULT))],
)
async def list_public_pay_providers(
    mngr: PaymentProvidersMngr = Depends(get_pay_providers_mngr),
    pay_mngr: PayMngr = Depends(get_pay_mngr),
) -> list[PayProviderPublic]:
    """Список доступных платёжных провайдеров для витрины."""
    rows = await mngr.list_enabled()
    available_fx: set[str] | None = None
    if pay_mngr.fx is not None:
        try:
            available_fx = await pay_mngr.fx.get_available_currencies()
        except Exception:
            available_fx = None

    res: list[PayProviderPublic] = []
    for p in rows:
        supported = [p.currency] + [c for c in (p.currencies or []) if c != p.currency]
        if available_fx is not None:
            filtered = [c for c in supported if c.upper() in available_fx]
        else:
            filtered = supported
        res.append(PayProviderPublic.from_model(p, available_currencies=filtered))
    return res


@router.post(
    "/purchases/create",
    response_model=GuestPurchaseResult,
    status_code=status.HTTP_201_CREATED,
    summary="Create guest purchase",
    description="Creates an order and payment invoice without requiring login.",
    dependencies=[Depends(rate_limit("public.purchases.create", LimitKind.SENSITIVE))],
)
async def create_guest_purchase(
    request: Request,
    body: GuestPurchaseCreate,
    session: AsyncSession = Depends(get_db_session),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    guest_svc: GuestCheckoutSvc = Depends(get_guest_checkout_svc),
    pay_mngr: PayMngr = Depends(get_pay_mngr),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    usvc_mngr: UserServicesMngr = Depends(get_usersvc_mngr),
    promo_mngr: PromoCodesMngr = Depends(get_promo_mngr),
    triggers: TriggerDispatcher = Depends(get_dispatcher),
) -> GuestPurchaseResult:
    """Оформить покупку услуги без предварительной авторизации."""
    # 1. Проверяем глобальный тумблер гостевого чекаута
    guest_enabled = await settings.get_bool("shop.guest_checkout.enabled", True)
    if not guest_enabled:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Guest checkout is disabled"
        )

    # 2. Валидация email
    norm_email = normalize_email(body.email)
    if not norm_email:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "invalid email address"
        )
    banned_domains = BannedEmailDomainsMngr(session)
    if await banned_domains.is_banned(norm_email):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "orders from this email domain are not allowed",
        )

    # 3. Валидация return_url
    if body.return_url:
        cfg: AppConfig = request.app.state.settings
        allowed = [*cfg.cors_origins_list, cfg.PUBLIC_URL.rstrip("/")]
        if not is_safe_return_url(body.return_url, allowed):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "return_url must be a relative path or a project origin",
            )

    # 4. Проверка существования аккаунта и политики существующих пользователей
    user_mngr = UserMngr(session)
    existing = await user_mngr.by_email(norm_email)
    requires_auth = False

    if existing is None:
        # Создаём новый гостевой аккаунт
        login = f"guest:{secrets.token_hex(6)}"
        acc = await user_mngr.create(login, None, norm_email, role_key=BaseRole.GUEST)
        await session.flush()
    else:
        # Проверяем роль существующего пользователя
        role_key = existing.role.key if existing.role else BaseRole.GUEST
        if role_key == BaseRole.GUEST:
            acc = existing
        else:
            # Пользователь уже зарегистрирован и верифицирован (role != guest)
            policy = await settings.get(
                "shop.guest_checkout.existing_user_policy", "allow_require_auth_to_view"
            )
            if policy == "require_login":
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail={
                        "code": "EMAIL_REQUIRES_LOGIN",
                        "message": "An account with this email already exists. Please log in to complete purchase.",
                    },
                )
            # allow_require_auth_to_view: заказ вяжется к юзеру, но требует логина для просмотра
            acc = existing
            requires_auth = True

    # 5. Авторитетный расчёт стоимости заказа (Zero Trust)
    service = await svc_mngr.get_active(body.service_id)
    resolved = resolve_service_order(
        service,
        custom_amount=body.custom_amount,
        tier_code=body.tier_code,
        components=body.components,
        form=body.form,
    )
    base_price = resolved.price

    # 6. Промокоды
    discount = Decimal("0")
    promo_id: int | None = None
    if body.promocode:
        promo = await promo_mngr.load_valid(body.promocode, acc)
        catalog = await promo_mngr.catalog_of(promo)
        if catalog.kind != PromoKind.DISCOUNT:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "promo code is not a discount code"
            )
        discount = promo_mngr.discount_for(catalog, service, base_price=base_price)
        promo_id = promo.id

    amount = base_price - discount
    if amount <= Decimal("0"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "service is fully discounted by promo code, log in to order free services",
        )

    # 7. Создаём отложенную выдачу услуги (UserServicesModel)
    usvc = await usvc_mngr.create(
        acc,
        service,
        discount=discount,
        custom_amount=body.custom_amount,
        tier_code=body.tier_code,
        components=body.components,
        form=body.form,
        charge=False,
        deliver=False,
    )
    if promo_id is not None:
        usvc.private_data = {**(usvc.private_data or {}), "promocode_id": promo_id}

    # 8. Создаём платёж
    payment = await pay_mngr.create(
        acc,
        amount,
        body.provider,
        target=PayTarget.SERVICE,
        user_svc_id=usvc.id,
        currency=body.currency,
        return_url=body.return_url,
    )

    # 9. Генерируем защищённый разовый токен просмотра заказа
    order_token = await guest_svc.create_order_view_token(
        order_id=usvc.id,
        payment_id=payment.id,
        account_id=acc.id,
        requires_auth=requires_auth,
    )

    await pay_mngr.s.commit()

    # 10. Триггер создания заказа
    await triggers.fire(
        TriggerEvent.ORDER_CREATED,
        {
            "order": {
                "id": usvc.id,
                "service_id": body.service_id,
                "via": "guest_checkout",
            },
            "user": {"id": acc.id, "login": acc.login, "email": acc.email},
            "guest": True,
        },
    )

    return GuestPurchaseResult(
        payment_id=payment.id,
        user_svc_id=usvc.id,
        amount=payment.amount,
        currency=payment.currency,
        pay_url=payment.payment_url,
        order_token=order_token,
        status=payment.status,
        requires_auth=requires_auth,
    )


@router.get(
    "/orders/{order_id}",
    response_model=PublicOrderView,
    summary="Get public order details by secure token",
    description="Returns order status and purchased product keys. Masks sensitive data if requires_auth is true.",
    dependencies=[Depends(rate_limit("public.orders.view", LimitKind.DEFAULT))],
)
async def get_public_order_status(
    order_id: int,
    token: str = Query(..., description="Secure order access token"),
    guest_svc: GuestCheckoutSvc = Depends(get_guest_checkout_svc),
    usvc_mngr: UserServicesMngr = Depends(get_usersvc_mngr),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    pay_mngr: PayMngr = Depends(get_pay_mngr),
    user_mngr: UserMngr = Depends(lambda s=Depends(get_db_session): UserMngr(s)),
) -> PublicOrderView:
    """Публичный просмотр заказа по защищённому токену."""
    payload = await guest_svc.get_order_token_payload(token)
    if not payload or payload.get("order_id") != order_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "order token is invalid or expired"
        )

    usvc = await usvc_mngr.by_id(order_id)
    if not usvc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "order not found")

    payment_id = payload.get("payment_id")
    payment: UserPaymentsModel | None = None
    if payment_id:
        payment = await pay_mngr.s.get(UserPaymentsModel, payment_id)

    service = await svc_mngr.by_id(usvc.service_id)
    acc = await user_mngr.by_id(usvc.account_id)
    masked_email = mask_email(acc.email or "") if acc else "***"

    requires_auth = bool(payload.get("requires_auth"))

    # Если требуется авторизация (заказ привязан к существующему юзеру),
    # ключи и конфиденциальные данные скрываются
    keys: list[str] | None = None
    public_data: dict[str, Any] | None = None

    if not requires_auth:
        public_data = usvc.public_data or {}
        # Извлекаем ключи если есть
        extracted_keys: list[str] = []
        if usvc.public_data:
            prod = usvc.public_data.get("product") or usvc.public_data.get("key")
            if prod:
                extracted_keys.append(str(prod))
            items = usvc.public_data.get("keys")
            if isinstance(items, list):
                extracted_keys.extend(str(k) for k in items)
        keys = extracted_keys if extracted_keys else None

    return PublicOrderView(
        order_id=usvc.id,
        service_id=usvc.service_id,
        service_name=service.name if service else "Service",
        status=usvc.status,
        payment_status=payment.status if payment else "unknown",
        amount=usvc.price,
        currency=payment.currency if payment else "USD",
        created_at=usvc.created_at,
        keys=keys,
        public_data=public_data,
        requires_auth=requires_auth,
        buyer_email_masked=masked_email,
    )


__all__ = ["router"]
