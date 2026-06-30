"""Авто-документация требований роутов (права, лимиты, авторизация) в OpenAPI."""

from __future__ import annotations

from typing import Iterator

from fastapi import FastAPI
from fastapi.routing import APIRoute

from dependencies.auth import get_current_acc
from dependencies.ratelimit import LimitKind
from utils.config import AppConfig

_DOCUMENTED = "_perms_documented"


def _iter_api_routes(routes) -> Iterator[APIRoute]:
    """Рекурсивно обойти роуты, разворачивая вложенные/отложенные роутеры."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
            continue
        # starlette >= 1.3 оборачивает include_router в отложенный роутер.
        nested = getattr(route, "original_router", None) or getattr(
            route, "routes", None
        )
        if nested is not None:
            inner = getattr(nested, "routes", nested)
            yield from _iter_api_routes(inner)


def _route_perms(route: APIRoute) -> list[str]:
    """Собрать требуемые права роута из его зависимостей.

    :arg route: маршрут API.
    :return: список ключей прав.
    """
    perms: list[str] = []
    for dep in route.dependant.dependencies:
        perm = getattr(dep.call, "_required_perm", None)
        if perm and perm not in perms:
            perms.append(perm)
    return perms


def _route_limits(route: APIRoute) -> list[LimitKind]:
    """Собрать категории rate-лимита роута.

    :arg route: маршрут API.
    :return: список категорий лимита.
    """
    kinds: list[LimitKind] = []
    for dep in route.dependant.dependencies:
        kind = getattr(dep.call, "_rate_limit_kind", None)
        if kind is not None and kind not in kinds:
            kinds.append(kind)
    return kinds


def _needs_auth(dependant) -> bool:
    """Требует ли роут access-токен (наличие ``get_current_acc`` в дереве).

    :arg dependant: корневой dependant маршрута.
    :return: ``True`` если нужен Bearer-токен.
    """
    stack = list(dependant.dependencies)
    while stack:
        dep = stack.pop()
        if dep.call is get_current_acc:
            return True
        stack.extend(dep.dependencies)
    return False


def _limit_text(cfg: AppConfig, kind: LimitKind) -> str:
    """Человекочитаемое правило лимита для категории.

    :arg cfg: конфигурация приложения.
    :arg kind: категория лимита.
    :return: строка вида ``N запросов / M c``.
    """
    if kind is LimitKind.AUTH:
        mx, win = cfg.RATE_LIMIT_AUTH_MAX, cfg.RATE_LIMIT_AUTH_WINDOW
    elif kind is LimitKind.MAIL:
        mx, win = cfg.RATE_LIMIT_MAIL_MAX, cfg.RATE_LIMIT_MAIL_WINDOW
    else:
        mx, win = cfg.RATE_LIMIT_DEFAULT_MAX, cfg.RATE_LIMIT_DEFAULT_WINDOW
    return f"{mx} запросов / {win} c"


def document_perms(app: FastAPI) -> None:
    """Дописать в описание роутов права, ограничения и требование авторизации.

    :arg app: приложение FastAPI (его ``state.settings`` — источник правил лимитов).
    """
    cfg: AppConfig | None = getattr(app.state, "settings", None)

    for route in _iter_api_routes(app.routes):
        if getattr(route, _DOCUMENTED, False):
            continue

        notes: list[str] = []

        if _needs_auth(route.dependant):
            notes.append("**Авторизация:** Bearer access-токен")

        perms = _route_perms(route)
        if perms:
            joined = ", ".join(f"`{p}`" for p in perms)
            notes.append(f"**Требуемые права:** {joined}")

        limits = _route_limits(route)
        if limits and cfg is not None:
            joined = "; ".join(_limit_text(cfg, k) for k in limits)
            notes.append(f"**Ограничение частоты:** {joined}")

        if not notes:
            continue

        route.description = (route.description or "") + "\n\n" + "\n\n".join(notes)
        setattr(route, _DOCUMENTED, True)

    # Сбросить кэш схемы, чтобы изменения попали в /openapi.json.
    app.openapi_schema = None


__all__ = ["document_perms"]
