"""Контракты триггеров (событие → действие)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Trigger(BaseModel):
    """Trigger."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None = None
    event: str
    action: str
    config: dict
    cond: dict
    is_active: bool

    @classmethod
    def from_model(cls, m) -> "Trigger":  # noqa: ANN001 — TriggerModel
        """Явное преобразование ORM-триггера в схему.

        :arg m: модель триггера.
        :return: схема ответа.
        """
        return cls.model_validate(m)


class TriggerCreate(BaseModel):
    """Create trigger."""

    name: str | None = Field(
        default=None, max_length=128, description="Trigger name (optional)"
    )
    event: str = Field(min_length=2, max_length=64, description="Event condition")
    action: str = Field(
        min_length=2,
        max_length=32,
        description="Action key: email | lua",
    )
    config: dict = Field(default_factory=dict, description="Action params (optional)")
    cond: dict = Field(default_factory=dict, description="Extra conditions (optional)")
    is_active: bool = Field(default=True, description="Active (optional)")


class TriggerPatch(BaseModel):
    """Update trigger."""

    name: str | None = Field(default=None, description="Trigger name")
    event: str | None = Field(
        default=None, min_length=2, max_length=64, description="Event condition"
    )
    action: str | None = Field(
        default=None, min_length=2, max_length=32, description="Action key"
    )
    config: dict | None = Field(default=None, description="Action params")
    cond: dict | None = Field(default=None, description="Extra conditions")
    is_active: bool | None = Field(default=None, description="Active")


class TriggerMeta(BaseModel):
    """Available events and actions."""

    events: list[str]
    actions: list[str]


__all__ = ["Trigger", "TriggerCreate", "TriggerPatch", "TriggerMeta"]
