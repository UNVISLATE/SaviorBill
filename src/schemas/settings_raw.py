"""Контракты ручного (raw) управления таблицей ``settings`` (админ)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from models.system_settings import SystemSettingsModel
from core.settings_def import SettingDef


def effective_group(key: str, spec: SettingDef | None) -> str:
    """Группа для отображения в raw-редакторе: из каталога, либо первый
    сегмент ключа (для произвольных ключей без записи в каталоге)."""
    if spec is not None:
        return spec.group
    return key.split(".", 1)[0] if "." in key else "other"


class SettingRawOut(BaseModel):
    """Raw settings row."""

    key: str = Field(description="Setting key")
    value: str | None = Field(description="Value; null for secrets")
    is_secret: bool = Field(description="Stored encrypted")
    editable: bool = Field(description="Editable via raw routes")
    group: str = Field(description="Settings group (catalog group, or key prefix for ad-hoc keys)")
    desc: str | None = Field(default=None, description="Settings catalog description")
    created_at: datetime = Field(description="Created at")
    updated_at: datetime = Field(description="Updated at")

    @classmethod
    def from_model(
        cls, row: SystemSettingsModel, spec: SettingDef | None
    ) -> "SettingRawOut":
        return cls(
            key=row.key,
            value=None if row.is_secret else row.value,
            is_secret=row.is_secret,
            editable=not row.is_secret,
            group=effective_group(row.key, spec),
            desc=spec.desc if spec else None,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class SettingsGroupOut(BaseModel):
    """One prefix/group in the raw settings list (for the two-level admin UI)."""

    name: str = Field(description="Group name")
    count: int = Field(description="Number of settings rows in this group")


class SettingRawUpsert(BaseModel):
    """Upsert raw setting."""

    value: str | None = Field(description="New value or null")


__all__ = ["SettingRawOut", "SettingRawUpsert", "SettingsGroupOut", "effective_group"]
