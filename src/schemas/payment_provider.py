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

    slug: str = Field(
        min_length=2,
        max_length=64,
        description="Уникальный slug провайдера (обязательно)",
    )
    title: str | None = Field(
        default=None, description="Отображаемое имя (опционально)"
    )
    enabled: bool = Field(
        default=False, description="Включён ли провайдер (опционально)"
    )
    currency: str = Field(
        default="RUB", max_length=8, description="Валюта по умолчанию (опционально)"
    )
    secrets: dict = Field(
        default_factory=dict,
        description="JSON секретов/доп-данных платёжки, шифруется при сохранении (опционально)",
    )
    init_script_id: int | None = Field(
        default=None, description="ID lua-скрипта инициализации платежа (опционально)"
    )
    cb_script_id: int | None = Field(
        default=None, description="ID lua-скрипта обработки колбэка (опционально)"
    )
    extra: dict = Field(
        default_factory=dict, description="Несекретные доп-параметры (опционально)"
    )


class PayProviderPatch(BaseModel):
    """Изменение платёжного провайдера (только переданные поля)."""

    title: str | None = Field(default=None, description="Отображаемое имя")
    enabled: bool | None = Field(default=None, description="Включён ли провайдер")
    currency: str | None = Field(default=None, description="Валюта по умолчанию")
    secrets: dict | None = Field(
        default=None, description="Новый JSON секретов (перешифровывается)"
    )
    init_script_id: int | None = Field(
        default=None, description="ID lua-скрипта инициализации"
    )
    cb_script_id: int | None = Field(default=None, description="ID lua-скрипта колбэка")
    extra: dict | None = Field(default=None, description="Несекретные доп-параметры")


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
