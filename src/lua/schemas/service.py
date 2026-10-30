"""Схема эталонной услуги для контекста Lua (все поля услуги)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer


class LuaService(BaseModel):
    """Reference service for Lua."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    description: str | None = None
    catalog_id: int | None = None
    price: Decimal
    currency: str = "RUB"
    price_type: str = "fixed"
    pricing_config: dict = {}
    delivery: str
    lua_script_id: int | None = None
    duration: int | None = None
    actions: list = []
    params: dict = {}
    settings: dict = {}
    is_active: bool = True

    @field_serializer("price")
    def _money(self, v: Decimal) -> str:
        return str(v)

    @classmethod
    def from_model(cls, m) -> "LuaService":  # noqa: ANN001 — ServiceModel
        """Собрать из ORM-услуги."""
        return cls(
            id=m.id,
            slug=m.slug,
            name=m.name,
            description=m.description,
            catalog_id=m.catalog_id,
            price=m.price,
            currency=getattr(m, "currency", "RUB") or "RUB",
            price_type=getattr(m, "price_type", "fixed") or "fixed",
            pricing_config=getattr(m, "pricing_config", {}) or {},
            delivery=m.delivery,
            lua_script_id=m.lua_script_id,
            duration=m.duration,
            actions=getattr(m, "actions", []) or [],
            params=getattr(m, "params", {}) or {},
            settings=getattr(m, "settings", {}) or {},
            is_active=True if getattr(m, "is_active", True) is None else getattr(m, "is_active", True),
        )


__all__ = ["LuaService"]
