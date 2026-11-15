"""Схема данных самого шаблона (скрипта) для контекста Lua: ``ctx.lua.*``."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LuaMeta(BaseModel):
    """Script metadata and settings."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str | None = None
    kind: str
    actions: list = Field(default_factory=list)
    settings: dict = Field(default_factory=dict)

    @classmethod
    def from_model(cls, m) -> "LuaMeta":  # noqa: ANN001 — SystemScriptsModel
        """Преобразовать ORM-скрипт в схему контекста ``lua``."""
        return cls.model_validate(m)


__all__ = ["LuaMeta"]
