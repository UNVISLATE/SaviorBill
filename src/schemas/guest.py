"""Схемы для гостевого чекаута, клейма аккаунтов и публичного просмотра заказов."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from schemas.types import OptNormEmail


class GuestClaimRequest(BaseModel):
    """Запрос кода подтверждения для гостевого аккаунта."""

    email: str = Field(min_length=3, max_length=255, description="Email гостевого аккаунта")


class GuestClaimRequestResult(BaseModel):
    """Результат запроса OTP-кода подтверждения."""

    claim_token: str = Field(description="Токен сессии клейма")
    ttl_seconds: int = Field(description="Время жизни кода в секундах")


class GuestClaimVerify(BaseModel):
    """Подтверждение владения гостевым аккаунтом и установка пароля."""

    claim_token: str = Field(min_length=16, max_length=128, description="Токен сессии клейма")
    code: str = Field(min_length=4, max_length=16, description="Код подтверждения из письма")
    password: str = Field(min_length=8, max_length=128, description="Новый пароль (8–128 символов)")


class GuestPurchaseCreate(BaseModel):
    """Создание заказа и инвойса через гостевой чекаут."""

    email: str = Field(min_length=3, max_length=255, description="Email покупателя")
    provider: str = Field(description="Слаг платёжного провайдера")
    service_id: int = Field(description="ID приобретаемой услуги")
    currency: str | None = Field(default=None, max_length=8, description="Желаемая валюта оплаты (опционально)")
    custom_amount: Decimal | None = Field(
        default=None, gt=0, description="Произвольная сумма для price_type=custom"
    )
    tier_code: str | None = Field(
        default=None, max_length=64, description="Код тарифа для price_type=tiered"
    )
    components: dict[str, Any] | None = Field(
        default=None, description="Компоненты для price_type=configurable"
    )
    form: dict[str, Any] | None = Field(
        default=None, description="Поля формы клиента"
    )
    return_url: str | None = Field(
        default=None, description="URL возврата после оплаты"
    )
    promocode: str | None = Field(
        default=None, max_length=64, description="Промокод на скидку"
    )


class GuestPurchaseResult(BaseModel):
    """Результат оформления гостевого заказа."""

    payment_id: int
    user_svc_id: int
    amount: Decimal
    currency: str
    pay_url: str | None = None
    order_token: str
    status: str
    requires_auth: bool = False


class PublicOrderView(BaseModel):
    """Публичный статус и данные заказа по защищённому токену."""

    order_id: int
    service_id: int
    service_name: str
    status: str
    payment_status: str
    amount: Decimal
    currency: str
    created_at: datetime
    keys: list[str] | None = None
    instructions_md: str | None = Field(default=None, description="Инструкция по активации в формате Markdown")
    public_data: dict[str, Any] | None = None
    requires_auth: bool = False
    buyer_email_masked: str
