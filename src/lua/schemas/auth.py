"""Схема OAuth-провайдера для контекста Lua (auth-скрипты)."""

from __future__ import annotations

from pydantic import BaseModel


class LuaAuthProvider(BaseModel):
    """OAuth provider data for Lua auth."""

    slug: str
    title: str | None = None
    scopes: str = ""
    secrets: dict = {}
    extra: dict = {}

    @classmethod
    def from_model(cls, prov, secrets: dict) -> "LuaAuthProvider":  # noqa: ANN001 — ORM
        """Собрать из ORM-провайдера и уже расшифрованных секретов."""
        return cls(
            slug=prov.slug,
            title=prov.title,
            scopes=prov.scopes or "",
            secrets=secrets or {},
            extra=prov.extra or {},
        )


__all__ = ["LuaAuthProvider"]
