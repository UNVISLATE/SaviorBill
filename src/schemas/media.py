"""Схемы медиа: загрузка/статус/регистрация/вложения (Request/Response).

Файлы физически обрабатывает mediaworker; billing хранит метаданные и решает
права/квоты. Публичный URL готового файла — относительный ``/media/{token}``
(домен подставляет фронтенд/Caddy).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


def _media_url(token: str) -> str:
    """Относительный URL отдачи медиа (обслуживает Caddy/mediaworker)."""
    return f"/media/{token}"


class Media(BaseModel):
    """Media item."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    token: str
    kind: str
    status: str
    url: str
    backend: str
    mime: str | None = None
    size: int | None = None
    owner_id: int | None = None
    variants: dict = Field(
        default_factory=dict,
        description="File variants by key, mime, size, url",
    )

    @classmethod
    def from_model(cls, m) -> "Media":  # noqa: ANN001 — SystemMediaModel
        """Преобразование ORM-записи медиа в схему ответа."""
        return cls(
            id=m.id,
            token=m.token,
            kind=m.kind,
            status=m.status,
            url=_media_url(m.token),
            backend=m.backend,
            mime=m.mime,
            size=m.size,
            owner_id=m.owner_id,
            variants=m.variants or {},
        )


class MediaTask(BaseModel):
    """Upload accepted response."""

    token: str = Field(description="Media/task token")
    status: str = Field(description="Status: processing | ready | failed")


class MediaStatus(BaseModel):
    """Conversion status."""

    token: str = Field(description="Media/task token")
    state: str = Field(description="processing | ready | failed")
    url: str | None = Field(
        default=None, description="Ready file URL (optional)"
    )
    mime: str | None = Field(
        default=None, description="Ready file MIME (optional)"
    )
    error: str | None = Field(default=None, description="Error text (optional)")


class Attachment(BaseModel):
    """Service attachment."""

    id: int
    media_id: int
    token: str
    kind: str
    tag: str | None = None
    position: int
    mime: str | None = None
    status: str
    url: str

    @classmethod
    def from_model(cls, m) -> "Attachment":  # noqa: ANN001 — ServiceAttachmentModel
        """Построить схему из ORM-вложения (с подгруженным ``media``)."""
        media = m.media
        return cls(
            id=m.id,
            media_id=m.media_id,
            token=media.token,
            kind=media.kind,
            tag=m.tag,
            position=m.position,
            mime=media.mime,
            status=media.status,
            url=_media_url(media.token),
        )


class AttachmentIn(BaseModel):
    """Add service attachment."""

    media_id: int = Field(description="Media ID")
    tag: str | None = Field(
        default=None,
        max_length=16,
        description="Attachment tag, up to 16 chars",
    )
    position: int = Field(default=0, description="Sort order (optional)")


__all__ = [
    "Media",
    "MediaTask",
    "MediaStatus",
    "Attachment",
    "AttachmentIn",
]
