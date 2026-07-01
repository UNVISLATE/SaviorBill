"""Схема эталонной услуги для контекста Lua (все поля услуги)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer


class LuaService(BaseModel):
    """Эталонная услуга для Lua-скрипта.

    ``duration`` — первоклассный атрибут услуги (срок действия в секундах), а не
    настройка. ``settings`` — JSON эталонной услуги (``service.settings.*``),
    ``params`` — кастом-параметры услуги.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    description: str | None = None
    catalog_id: int | None = None
    price: Decimal
    currency: str = "RUB"
    delivery: str
    lua_script_id: int | None = None
    duration: int | None = None
    actions: list = []
    params: dict = {}
    settings: dict = {}
    image: str | None = None
    is_active: bool = True

    @field_serializer("price")
    def _money(self, v: Decimal) -> str:
        return str(v)

    @classmethod
    def from_model(cls, m) -> "LuaService":  # noqa: ANN001 — ServiceModel
        """Собрать из ORM-услуги."""
        return cls.model_validate(m)


__all__ = ["LuaService"]
