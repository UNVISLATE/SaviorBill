"""Триггеры: событие → действие (email, lua, …). Диспетчер и реестр действий."""

from __future__ import annotations

import logging

from models.system_settings import SystemSettingsMngr
from models.triggers import TriggerMngr

from .base import BaseAction, dig
from .email_action import EmailAction
from .events import ALL_EVENTS, TriggerEvent

log = logging.getLogger("saviorbill.triggers")

# Ключи доступных действий (для валидации и UI). "lua" — ключ
# lua.integrations.trigger_action.LuaAction; не импортируем класс здесь,
# чтобы не создавать цикл lifecycle.triggers <-> lua.integrations.
ACTION_KEYS = [EmailAction.key, "lua"]

_DEFAULT_MAX_RETRIES = 3
_DEFAULT_MAX_FIRES_PER_MINUTE = 60


class TriggerDispatcher:
    """Поиск и исполнение действий триггеров события (best-effort)."""

    def __init__(
        self,
        triggers: TriggerMngr,
        actions: dict[str, BaseAction],
        settings: SystemSettingsMngr | None = None,
    ) -> None:
        self.triggers = triggers
        self.actions = actions
        self.settings = settings

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

    async def _allow_event(self, event: str) -> bool:
        """Анти-петля: не более N срабатываний события в минуту (Valkey-счётчик).

        Без ``settings`` (например, вне HTTP-запроса) лимит не проверяется —
        считаем это осознанным ограничением области действия анти-петли.

        :arg event: имя доменного события.
        :return: ``True`` если срабатывание разрешено.
        """
        if self.settings is None:
            return True
        try:
            limit = await self.settings.get_int(
                "triggers.max_fires_per_event_per_minute",
                _DEFAULT_MAX_FIRES_PER_MINUTE,
            )
            limit = limit or _DEFAULT_MAX_FIRES_PER_MINUTE
            key = f"triggers:fire:{event}"
            n = await self.settings.vk.incr(key)
            if n == 1:
                await self.settings.vk.expire(key, 60)
            if n > limit:
                log.warning(
                    "триггеры: анти-петля — событие %s превысило лимит %s/мин",
                    event,
                    limit,
                )
                return False
        except Exception:  # noqa: BLE001 — анти-петля не должна ломать событие
            log.exception("триггеры: ошибка анти-петли для %s", event)
        return True

    async def fire(self, event: str, ctx: dict) -> int:
        """Исполнить все подходящие триггеры события.

        Никогда не бросает: ошибки логируются и пропускаются. Каждое
        действие повторяется до ``triggers.max_retries`` раз (без этого
        сбойное действие могло бы либо остановиться после первой ошибки
        без всякой попытки восстановиться, либо — при наивном retry-цикле
        без предела — зациклиться и повесить обработку события).

        :arg event: имя доменного события.
        :arg ctx: контекст события.
        :return: число успешно выполненных действий.
        """
        if not await self._allow_event(event):
            return 0

        try:
            rows = await self.triggers.by_event(event)
        except Exception:  # noqa: BLE001
            log.exception("триггеры: ошибка выборки для %s", event)
            return 0

        max_retries = _DEFAULT_MAX_RETRIES
        if self.settings is not None:
            try:
                max_retries = (
                    await self.settings.get_int(
                        "triggers.max_retries", _DEFAULT_MAX_RETRIES
                    )
                    or _DEFAULT_MAX_RETRIES
                )
            except Exception:  # noqa: BLE001
                log.exception("триггеры: ошибка чтения triggers.max_retries")

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
            ok = False
            for attempt in range(1, max(1, max_retries) + 1):
                try:
                    if await action.run(event, ctx, trig.config or {}):
                        ok = True
                        break
                except Exception:  # noqa: BLE001 — триггер не должен ломать операцию
                    log.exception(
                        "триггер #%s (%s/%s): ошибка, попытка %s/%s",
                        trig.id,
                        event,
                        trig.action,
                        attempt,
                        max_retries,
                    )
            if ok:
                done += 1
        return done


__all__ = [
    "TriggerDispatcher",
    "TriggerEvent",
    "ALL_EVENTS",
    "ACTION_KEYS",
    "BaseAction",
    "EmailAction",
    "dig",
]
