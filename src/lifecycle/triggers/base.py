"""Базовый интерфейс действий триггеров."""

from __future__ import annotations


def dig(ctx: dict, path: str):
    """Достать значение из вложенного словаря по пути ``a.b.c``.

    :arg ctx: контекст события.
    :arg path: точечный путь.
    :return: значение или ``None``.
    """
    cur = ctx
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


class BaseAction:
    """Действие триггера. Конкретные действия — в automation/triggers/*."""

    key: str = ""

    async def run(self, event: str, ctx: dict, config: dict) -> bool:
        """Выполнить действие для события.

        :arg event: идентификатор доменного события.
        :arg ctx: контекст события (данные пользователя/платежа/услуги …).
        :arg config: параметры действия из триггера.
        :return: ``True`` если действие выполнено.
        """
        raise NotImplementedError


__all__ = ["BaseAction", "dig"]
