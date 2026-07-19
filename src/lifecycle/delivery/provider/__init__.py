"""Нативные провайдеры выдачи услуг (стратегии доставки).

Lua-провайдер (``LuaService``) — не здесь, а в ``lua.integrations.delivery``
(см. ``lifecycle.delivery.get_issuer`` — импортирует его лениво, чтобы не
создавать цикл между пакетами lifecycle и lua)."""

from __future__ import annotations

from .key_service import KeyService

__all__ = ["KeyService"]
