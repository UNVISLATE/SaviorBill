"""Контракты триггеров (событие → действие)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Trigger(BaseModel):
    """Триггер (ответ)."""

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
    """Создание триггера.

    ``action`` — ключ действия (``email``/``lua``). ``config`` — его параметры
    (email: ``template_id``/``to_field``; lua: ``script_id``).
    """

    name: str | None = Field(
        default=None, max_length=128, description="Имя триггера (опционально)"
    )
    event: str = Field(
        min_length=2, max_length=64, description="Событие-условие (обязательно)"
    )
    action: str = Field(
        min_length=2,
        max_length=32,
        description="Ключ действия: email | lua (обязательно)",
    )
    config: dict = Field(
        default_factory=dict, description="Параметры действия (опционально)"
    )
    cond: dict = Field(
        default_factory=dict, description="Доп-условия срабатывания (опционально)"
    )
    is_active: bool = Field(
        default=True, description="Активен ли триггер (опционально)"
    )


class TriggerPatch(BaseModel):
    """Изменение триггера (только переданные поля)."""

    name: str | None = Field(default=None, description="Имя триггера")
    event: str | None = Field(
        default=None, min_length=2, max_length=64, description="Событие-условие"
    )
    action: str | None = Field(
        default=None, min_length=2, max_length=32, description="Ключ действия"
    )
    config: dict | None = Field(default=None, description="Параметры действия")
    cond: dict | None = Field(default=None, description="Доп-условия срабатывания")
    is_active: bool | None = Field(default=None, description="Активен ли триггер")


class TriggerMeta(BaseModel):
    """Справочник для UI: доступные события и действия."""

    events: list[str]
    actions: list[str]


__all__ = ["Trigger", "TriggerCreate", "TriggerPatch", "TriggerMeta"]
