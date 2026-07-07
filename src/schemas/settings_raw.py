"""Контракты ручного (raw) управления таблицей ``settings`` (админ)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from models.system_settings import SystemSettingsModel
from utils.settings_def import SettingDef


class SettingRawOut(BaseModel):
    """Строка таблицы ``settings`` в raw-представлении.

    :arg key: ключ настройки.
    :arg value: значение (``None`` для зашифрованных — не раскрываем содержимое).
    :arg is_secret: хранится ли значение зашифрованным (SecBox).
    :arg editable: можно ли редактировать/удалять через raw-роуты (``False`` для секретов).
    :arg group: логическая группа из каталога настроек (если ключ зарегистрирован).
    :arg desc: описание из каталога настроек (если ключ зарегистрирован).
    :arg created_at: время создания записи.
    :arg updated_at: время последнего изменения записи.
    """

    key: str = Field(description="Ключ настройки (обязательно)")
    value: str | None = Field(description="Значение (null для секретов)")
    is_secret: bool = Field(description="Хранится ли значение зашифрованным")
    editable: bool = Field(description="Доступно ли редактирование через raw-роуты")
    group: str | None = Field(default=None, description="Группа из каталога настроек")
    desc: str | None = Field(default=None, description="Описание из каталога настроек")
    created_at: datetime = Field(description="Время создания записи")
    updated_at: datetime = Field(description="Время последнего изменения записи")

    @classmethod
    def from_model(
        cls, row: SystemSettingsModel, spec: SettingDef | None
    ) -> "SettingRawOut":
        return cls(
            key=row.key,
            value=None if row.is_secret else row.value,
            is_secret=row.is_secret,
            editable=not row.is_secret,
            group=spec.group if spec else None,
            desc=spec.desc if spec else None,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class SettingRawUpsert(BaseModel):
    """Тело записи/обновления значения настройки через raw-редактор.

    - `value`: новое значение (строка или `null`, чтобы очистить)
    """

    value: str | None = Field(description="Новое значение (или null)")


__all__ = ["SettingRawOut", "SettingRawUpsert"]
