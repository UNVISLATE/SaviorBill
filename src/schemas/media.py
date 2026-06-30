"""Схемы загрузки медиа (Request/Response)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Media(BaseModel):
    """Загруженный медиа-файл (ответ)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    url: str
    backend: str
    mime: str | None = None
    size: int | None = None

    @classmethod
    def from_model(cls, m) -> "Media":  # noqa: ANN001 — SystemMediaModel
        """Явное преобразование ORM-записи медиа в схему ответа.

        В БД путь хранится в ``path`` — наружу отдаём как ``url``.
        """
        return cls(
            id=m.id,
            kind=m.kind,
            url=m.path,
            backend=m.backend,
            mime=m.mime,
            size=m.size,
        )


__all__ = ["Media"]
