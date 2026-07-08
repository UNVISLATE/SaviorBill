"""Схемы управления пулом цифровых ключей услуги (админ)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ServiceKeyOut(BaseModel):
    """Ключ в списке — значение всегда замаскировано (право ``services.keys.read``)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    service_id: int
    is_used: bool
    used_at: datetime | None = None
    order_id: int | None = None
    created_at: datetime
    value: str = Field(
        default="***",
        description="Всегда замаскировано; реальное значение — через /reveal",
    )

    @classmethod
    def from_model(cls, m) -> "ServiceKeyOut":  # noqa: ANN001 — ServiceKeysModel
        return cls(
            id=m.id,
            service_id=m.service_id,
            is_used=m.is_used,
            used_at=m.used_at,
            order_id=m.order_id,
            created_at=m.created_at,
            value="***",
        )


class ServiceKeyRevealOut(BaseModel):
    """Раскрытое значение ключа (право ``ownersec.servicekeys.read``)."""

    id: int
    value: str


class ServiceKeysImportIn(BaseModel):
    """Массовый импорт ключей — готовый список, без парсинга свободного текста."""

    values: list[str] = Field(
        min_length=1,
        max_length=5000,
        description="Готовый список открытых значений ключей (фронт уже разбил текст)",
    )


class ServiceKeysImportOut(BaseModel):
    """Результат массового импорта."""

    added: int
    skipped: int = Field(description="Пропущено дублей внутри присланного списка")
    keys: list[ServiceKeyOut]


class ServiceStockOut(BaseModel):
    """Остаток цифровых ключей услуги — вычисляемый статус, не колонка БД."""

    service_id: int
    available: int
    out_of_stock: bool = Field(description="available == 0")

    @classmethod
    def build(cls, service_id: int, available: int) -> "ServiceStockOut":
        return cls(service_id=service_id, available=available, out_of_stock=available == 0)


__all__ = [
    "ServiceKeyOut",
    "ServiceKeyRevealOut",
    "ServiceKeysImportIn",
    "ServiceKeysImportOut",
    "ServiceStockOut",
]
