"""Схемы платёжных провайдеров (админ, Request/Response)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PayProvider(BaseModel):
    """Платёжный провайдер (ответ, без секретов)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str | None = None
    enabled: bool
    currency: str
    init_script_id: int | None = None
    cb_script_id: int | None = None
    extra: dict

    @classmethod
    def from_model(cls, m) -> "PayProvider":  # noqa: ANN001 — PaymentProvidersModel
        """Явное преобразование ORM-провайдера в схему ответа (без секретов)."""
        return cls.model_validate(m)


class PayProviderCreate(BaseModel):
    """Создание платёжного провайдера."""

    slug: str = Field(min_length=2, max_length=64)
    title: str | None = None
    enabled: bool = False
    currency: str = Field(default="RUB", max_length=8)
    # JSON секретов/доп-данных платёжки (шифруется при сохранении).
    secrets: dict = Field(default_factory=dict)
    init_script_id: int | None = None
    cb_script_id: int | None = None
    extra: dict = Field(default_factory=dict)


class PayProviderPatch(BaseModel):
    """Изменение платёжного провайдера (только переданные поля)."""

    title: str | None = None
    enabled: bool | None = None
    currency: str | None = None
    secrets: dict | None = None
    init_script_id: int | None = None
    cb_script_id: int | None = None
    extra: dict | None = None


class PayProviderPublic(BaseModel):
    """Платёжный провайдер для выбора пользователем (минимум полей)."""

    model_config = ConfigDict(from_attributes=True)

    slug: str
    title: str | None = None
    currency: str

    @classmethod
    def from_model(
        cls, m
    ) -> "PayProviderPublic":  # noqa: ANN001 — PaymentProvidersModel
        """Явное преобразование ORM-провайдера в публичную схему."""
        return cls.model_validate(m)


__all__ = [
    "PayProvider",
    "PayProviderCreate",
    "PayProviderPatch",
    "PayProviderPublic",
]
