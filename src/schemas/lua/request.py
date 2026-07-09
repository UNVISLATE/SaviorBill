"""Схема входящего HTTP-запроса для callback-скриптов платежей."""

from __future__ import annotations

from pydantic import BaseModel


class LuaRequest(BaseModel):
    """Webhook request data for Lua."""

    method: str = "POST"
    ip: str | None = None
    headers: dict = {}
    query: dict = {}
    body: dict = {}

    @classmethod
    def build(
        cls,
        *,
        method: str = "POST",
        ip: str | None = None,
        headers: dict | None = None,
        query: dict | None = None,
        body: dict | None = None,
    ) -> "LuaRequest":
        """Собрать схему запроса из компонентов FastAPI-запроса."""
        return cls(
            method=method,
            ip=ip,
            headers=headers or {},
            query=query or {},
            body=body or {},
        )


__all__ = ["LuaRequest"]
