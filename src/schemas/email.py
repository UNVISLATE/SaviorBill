"""Схемы email-шаблонов (Request/Response)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


# --- Шаблоны -----------------------------------------------------------------
class EmailTemplate(BaseModel):
    """Зарегистрированный email-шаблон (ответ)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str | None = None
    subject: str
    is_html: bool
    is_active: bool

    @classmethod
    def from_model(cls, m) -> "EmailTemplate":  # noqa: ANN001 — EmailModel
        """Явное преобразование ORM-шаблона в схему ответа."""
        return cls.model_validate(m)


class EmailTemplateDetail(EmailTemplate):
    """Зарегистрированный email-шаблон с телом (ответ на `GET /email/templates/{id}`).

    Отдельная схема от списка (`GET /email/templates`), чтобы список не тянул
    тела всех шаблонов из файлов — тело читается только при запросе одного.
    """

    body: str = Field(description="Тело письма, jinja2-шаблон")

    @classmethod
    def from_model_with_body(cls, m, body: str) -> "EmailTemplateDetail":  # noqa: ANN001
        """Явное преобразование ORM-шаблона + прочитанного тела в схему ответа."""
        return cls(
            id=m.id,
            slug=m.slug,
            name=m.name,
            subject=m.subject,
            is_html=m.is_html,
            is_active=m.is_active,
            body=body,
        )


class EmailTemplateUpload(BaseModel):
    """Регистрация нового шаблона.

    Имя файла тела генерируется системой. ``subject`` и ``body`` — jinja2.
    """

    slug: str = Field(
        min_length=2, max_length=64, description="Уникальный slug шаблона (обязательно)"
    )
    name: str | None = Field(
        default=None, max_length=128, description="Отображаемое имя (опционально)"
    )
    subject: str = Field(
        max_length=255, description="Тема, jinja2-строка (обязательно)"
    )
    body: str = Field(description="Тело письма, jinja2-шаблон (обязательно)")
    is_html: bool = Field(default=True, description="HTML или plain-text (опционально)")
    description: str | None = Field(
        default=None, max_length=2048, description="Описание (опционально)"
    )


class EmailTemplatePatch(BaseModel):
    """Изменение визуальных полей шаблона (без тела)."""

    name: str | None = Field(default=None, description="Отображаемое имя")
    subject: str | None = Field(
        default=None, max_length=255, description="Тема (jinja2)"
    )
    is_html: bool | None = Field(default=None, description="HTML или plain-text")
    description: str | None = Field(
        default=None, max_length=2048, description="Описание"
    )
    is_active: bool | None = Field(default=None, description="Активен ли шаблон")


class EmailBodyPatch(BaseModel):
    """Замена тела существующего шаблона."""

    body: str = Field(description="Новое тело письма (jinja2-шаблон)")


__all__ = [
    "EmailTemplate",
    "EmailTemplateDetail",
    "EmailTemplateUpload",
    "EmailTemplatePatch",
    "EmailBodyPatch",
]
