"""Реестр OAuth-провайдеров.

Скрипты-провайдеры регистрируют себя декоратором :func:`reg`. Чтобы добавить
платформу — создайте файл в ``providers/`` и пометьте класс ``@reg("slug")``.
"""

from __future__ import annotations

from typing import Type

from integrations.oauth.base import OIDCBase

_REG: dict[str, Type[OIDCBase]] = {}


def reg(slug: str):
    """Декоратор регистрации класса провайдера под заданным slug."""

    def wrap(cls: Type[OIDCBase]) -> Type[OIDCBase]:
        _REG[slug] = cls
        return cls

    return wrap


def get_provider(slug: str) -> Type[OIDCBase]:
    """Вернуть класс провайдера. Неизвестный slug -> generic OIDC."""
    return _REG.get(slug, OIDCBase)


def known() -> list[str]:
    """Список зарегистрированных slug'ов."""
    return sorted(_REG)


__all__ = ["reg", "get_provider", "known"]
