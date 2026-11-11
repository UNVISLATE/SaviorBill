"""Pydantic-схемы декларативных манифестов скриптов и Server-Driven UI (sbuiSDK).

Определяет структуру manifest.json для скриптов Lua:
- prefill: заготовки при создании сущностей
- media_download: безопасная загрузка статики/иконок через mediaworker
- settings_form: форма настроек провайдера/интеграции для администратора
- client_order_form: форма заказа для покупателя в витринном диалоге
- layout: декларативное дерево узлов интерфейса (SchemaNode)
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FieldType(StrEnum):
    """Типы полей ввода в формах манифеста."""

    TEXT = "text"
    PASSWORD = "password"
    NUMBER = "number"
    RANGE = "range"
    SELECT = "select"
    TOGGLE = "toggle"
    DATETIME = "datetime"
    TEXTAREA = "textarea"


class FieldOption(BaseModel):
    """Опция для выпадающего списка (select)."""

    value: str = Field(min_length=1, max_length=128, description="Уникальное значение опции")
    label: str = Field(min_length=1, max_length=256, description="Отображаемый текст")
    price_delta: Decimal = Field(default=Decimal("0"), description="Дельта стоимости (опционально)")


class FieldCondition(BaseModel):
    """Условие видимости/активности поля (depends_on)."""

    model_config = ConfigDict(populate_by_name=True)

    field: str = Field(min_length=1, max_length=128, description="Идентификатор родительского поля")
    equals: Any = Field(default=None, description="Ожидаемое значение")
    not_equals: Any = Field(default=None, description="Значение не должно быть равно")
    in_values: list[Any] | None = Field(
        default=None,
        alias="in",
        description="Значение должно входить в список",
    )
    not_in_values: list[Any] | None = Field(
        default=None,
        alias="not_in",
        description="Значение не должно входить в список",
    )


class FieldDefinition(BaseModel):
    """Декларативное описание поля формы (настроек или клиентского заказа)."""

    id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_.-]+$",
        description="Ключ поля (попадает в ctx.order.form.<id>)",
    )
    type: FieldType = Field(default=FieldType.TEXT, description="Тип элемента управления")
    label: str = Field(min_length=1, max_length=256, description="Человекочитаемый заголовок поля")
    placeholder: str | None = Field(default=None, max_length=256, description="Подсказка в поле ввода")
    description: str | None = Field(default=None, max_length=1024, description="Подробное описание/инструкция")
    required: bool = Field(default=False, description="Обязательно ли поле к заполнению")
    default: Any = Field(default=None, description="Значение по умолчанию")

    # Числовые ограничения (для number и range)
    min: Decimal | None = Field(default=None, description="Минимальное значение")
    max: Decimal | None = Field(default=None, description="Максимальное значение")
    step: Decimal | None = Field(default=None, gt=0, description="Шаг изменения")

    # Текстовые ограничения и валидация
    regex: str | None = Field(default=None, max_length=512, description="Регулярное выражение для валидации")
    regex_error: str | None = Field(default=None, max_length=256, description="Текст ошибки при несовпадении с regex")
    min_length: int | None = Field(default=None, ge=0, description="Минимальная длина строки")
    max_length: int | None = Field(default=None, ge=1, description="Максимальная длина строки")

    # Опции выбора (для select)
    options: list[FieldOption] | None = Field(default=None, description="Варианты выбора для type=select")

    # Условная видимость
    depends_on: FieldCondition | None = Field(default=None, description="Условие отображения поля")

    @model_validator(mode="after")
    def _validate_field_constraints(self) -> "FieldDefinition":
        if self.type == FieldType.SELECT and not self.options:
            raise ValueError(f"Поле {self.id!r} типа select обязано содержать список options")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"Поле {self.id!r}: min ({self.min}) не может быть больше max ({self.max})")
        return self


class PrefillConfig(BaseModel):
    """Заготовки метаданных для быстрого создания сущностей в SaviorBill."""

    name: str | None = Field(default=None, max_length=256, description="Рекомендуемое название услуги/провайдера")
    icon_url: str | None = Field(default=None, max_length=1024, description="URL иконки для загрузки")
    description: str | None = Field(default=None, max_length=4096, description="Шаблонное описание")
    scopes: list[str] = Field(default_factory=list, description="Необходимые скоупы прав")


class MediaDownloadItem(BaseModel):
    """Элемент фоновой безопасной загрузки медиа через mediaworker."""

    url: str = Field(min_length=1, max_length=2048, description="URL внешнего медиа-ресурса")
    filename: str = Field(min_length=1, max_length=256, description="Имя сохраняемого файла")
    expected_mime: str | None = Field(default=None, max_length=64, description="Ожидаемый MIME-тип (e.g. image/svg+xml)")


class SchemaNode(BaseModel):
    """Узел абстрактного синтаксического дерева интерфейса (Server-Driven UI)."""

    model_config = ConfigDict(extra="allow")

    type: str = Field(
        min_length=1,
        max_length=64,
        description="Тип узла: card, row, column, grid, text, badge, divider, field, qr, copy_field, markdown",
    )
    variant: str | None = Field(default=None, max_length=64, description="Стилевой вариант (e.g. primary, success, h1)")
    content: str | None = Field(default=None, description="Текстовое содержимое узла")
    field_id: str | None = Field(default=None, max_length=64, description="Ссылка на поле из формы (если type=field)")
    gap: int | str | None = Field(default=None, description="Отступ между дочерними элементами")
    align: str | None = Field(default=None, max_length=32, description="Выравнивание (start, center, end, stretch)")
    children: list[SchemaNode] = Field(default_factory=list, description="Дочерние узлы интерфейса")
    props: dict[str, Any] = Field(default_factory=dict, description="Дополнительные свойства узла")


class ScriptManifest(BaseModel):
    """Корневой манифест скрипта интеграции Lua (manifest.json)."""

    model_config = ConfigDict(extra="allow")

    version: str = Field(default="1.0", description="Версия формата манифеста")
    name: str = Field(min_length=1, max_length=128, description="Имя интеграции")
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$", description="Уникальный слаг")
    description: str | None = Field(default=None, max_length=2048, description="Описание интеграции")
    author: str | None = Field(default=None, max_length=128, description="Автор или студия")

    prefill: PrefillConfig | None = Field(default=None, description="Заготовки для создания сущностей")
    media_download: list[MediaDownloadItem] = Field(
        default_factory=list,
        description="Медиа для безопасной фоновой загрузки",
    )
    settings_form: list[FieldDefinition] = Field(
        default_factory=list,
        description="Форма настроек провайдера (для администратора в Admin UI)",
    )
    client_order_form: list[FieldDefinition] = Field(
        default_factory=list,
        description="Форма заказа для покупателя (валидируется сервером и передаётся в ctx.order.form)",
    )
    layout: SchemaNode | None = Field(
        default=None,
        description="Кастомный Server-Driven UI макет для рендера в витрине",
    )
    view_layout: SchemaNode | None = Field(
        default=None,
        description="Server-Driven UI форма просмотра выданной услуги в профиле покупателя",
    )
    view_trigger_label: str | None = Field(
        default=None,
        max_length=128,
        description="Текст кнопки открытия формы просмотра услуги в профиле",
    )
    hide_key: bool | None = Field(
        default=None,
        description="Скрыть стандартный блок key в карточке услуги (когда используется только форма просмотра)",
    )


__all__ = [
    "FieldType",
    "FieldOption",
    "FieldCondition",
    "FieldDefinition",
    "PrefillConfig",
    "MediaDownloadItem",
    "SchemaNode",
    "ScriptManifest",
]
