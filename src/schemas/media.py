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
    """Запись медиа (админ-ответ)."""

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
        )


class MediaTask(BaseModel):
    """Ответ на приём загрузки (mediaworker)."""

    token: str = Field(description="Идентификатор медиа/задачи (file_id = task_token)")
    status: str = Field(description="Статус: processing | ready | failed")


class MediaStatus(BaseModel):
    """Статус конвертации (ответ status-эндпоинта)."""

    token: str = Field(description="Идентификатор медиа/задачи")
    state: str = Field(description="processing | ready | failed")
    url: str | None = Field(
        default=None, description="URL готового файла (опционально)"
    )
    mime: str | None = Field(
        default=None, description="MIME готового файла (опционально)"
    )
    error: str | None = Field(default=None, description="Текст ошибки (опционально)")


class MediaAuthzReq(BaseModel):
    """Запрос авторизации загрузки (mediaworker -> billing, /internal)."""

    user_token: str = Field(description="Access-JWT пользователя (обязательно)")
    kind: str = Field(
        default="image",
        description="Вид: image | video | icon | avatar (опционально)",
    )


class MediaAuthz(BaseModel):
    """Ответ авторизации загрузки (billing -> mediaworker, /internal)."""

    owner_id: int = Field(description="ID пользователя-владельца")
    max_bytes: int = Field(description="Максимально разрешённый размер файла (байты)")


class MediaRegister(BaseModel):
    """Регистрация готового медиа (mediaworker -> billing, /internal).

    Вызывается после успешной конвертации; billing создаёт запись в БД.
    """

    token: str = Field(description="Идентификатор медиа (обязательно)")
    kind: str = Field(description="Вид: image | video | icon | avatar (обязательно)")
    path: str = Field(description="Ключ файла в хранилище (обязательно)")
    backend: str = Field(default="fs", description="fs | s3 (опционально)")
    mime: str | None = Field(
        default=None, description="MIME итогового файла (опционально)"
    )
    size: int | None = Field(
        default=None, description="Размер файла в байтах (опционально)"
    )
    owner_id: int | None = Field(default=None, description="ID владельца (опционально)")


class Attachment(BaseModel):
    """Вложение товара (ответ)."""

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
    """Добавление вложения к товару (админ)."""

    media_id: int = Field(description="ID медиа из таблицы медиа (обязательно)")
    tag: str | None = Field(
        default=None,
        max_length=16,
        description="Тег вложения, ≤16 символов (опционально)",
    )
    position: int = Field(default=0, description="Порядок сортировки (опционально)")


__all__ = [
    "Media",
    "MediaTask",
    "MediaStatus",
    "MediaAuthzReq",
    "MediaAuthz",
    "MediaRegister",
    "Attachment",
    "AttachmentIn",
]
