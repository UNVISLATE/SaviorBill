"""Схемы email-шаблонов (Request/Response)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


# --- Шаблоны -----------------------------------------------------------------
class EmailTemplate(BaseModel):
    """Email template."""

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
    """Email template with body."""

    body: str = Field(description="Email body (Jinja2 template)")

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
    """Create email template."""

    slug: str = Field(
        min_length=2, max_length=64, description="Unique template slug"
    )
    name: str | None = Field(
        default=None, max_length=128, description="Display name (optional)"
    )
    subject: str = Field(
        max_length=255, description="Subject (Jinja2)"
    )
    body: str = Field(description="Email body (Jinja2 template)")
    is_html: bool = Field(default=True, description="HTML or plain text (optional)")
    description: str | None = Field(
        default=None, max_length=2048, description="Description (optional)"
    )


class EmailTemplatePatch(BaseModel):
    """Update template fields."""

    name: str | None = Field(default=None, description="Display name")
    subject: str | None = Field(
        default=None, max_length=255, description="Subject (Jinja2)"
    )
    is_html: bool | None = Field(default=None, description="HTML or plain text")
    description: str | None = Field(
        default=None, max_length=2048, description="Description"
    )
    is_active: bool | None = Field(default=None, description="Active")


class EmailBodyPatch(BaseModel):
    """Replace template body."""

    body: str = Field(description="New email body (Jinja2 template)")


__all__ = [
    "EmailTemplate",
    "EmailTemplateDetail",
    "EmailTemplateUpload",
    "EmailTemplatePatch",
    "EmailBodyPatch",
]
