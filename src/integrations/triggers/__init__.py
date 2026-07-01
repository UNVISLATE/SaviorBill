"""Триггеры: событие → действие (email, lua, …). Диспетчер и реестр действий."""

from __future__ import annotations

import logging

from models.triggers import TriggerMngr

from .base import BaseAction, dig
from .email_action import EmailAction
from .events import ALL_EVENTS, TriggerEvent
from .lua_action import LuaAction

log = logging.getLogger("saviorbill.triggers")

# Ключи доступных действий (для валидации и UI).
ACTION_KEYS = [EmailAction.key, LuaAction.key]


class TriggerDispatcher:
    """Поиск и исполнение действий триггеров события (best-effort)."""

    def __init__(self, triggers: TriggerMngr, actions: dict[str, BaseAction]) -> None:
        self.triggers = triggers
        self.actions = actions

    @staticmethod
    def _match(cond: dict, ctx: dict) -> bool:
        """Все пары ``{path: value}`` условия должны совпасть с контекстом.

        :arg cond: условие триггера.
        :arg ctx: контекст события.
        :return: ``True`` если условие выполнено (или пустое).
        """
        if not cond:
            return True
        return all(dig(ctx, path) == expected for path, expected in cond.items())

    async def fire(self, event: str, ctx: dict) -> int:
        """Исполнить все подходящие триггеры события.

        Никогда не бросает: ошибки логируются и пропускаются.

        :arg event: имя доменного события.
        :arg ctx: контекст события.
        :return: число успешно выполненных действий.
        """
        try:
            rows = await self.triggers.by_event(event)
        except Exception:  # noqa: BLE001
            log.exception("триггеры: ошибка выборки для %s", event)
            return 0

        done = 0
        for trig in rows:
            if not self._match(trig.cond or {}, ctx):
                continue
            action = self.actions.get(trig.action)
            if action is None:
                log.warning(
                    "триггер #%s: неизвестное действие %r", trig.id, trig.action
                )
                continue
            try:
                if await action.run(event, ctx, trig.config or {}):
                    done += 1
            except Exception:  # noqa: BLE001 — триггер не должен ломать операцию
                log.exception(
                    "триггер #%s (%s/%s): ошибка", trig.id, event, trig.action
                )
        return done


__all__ = [
    "TriggerDispatcher",
    "TriggerEvent",
    "ALL_EVENTS",
    "ACTION_KEYS",
    "BaseAction",
    "EmailAction",
    "LuaAction",
    "dig",
]
