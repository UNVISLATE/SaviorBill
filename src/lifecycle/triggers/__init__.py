"""Триггеры: событие → действие (email, lua, …). Диспетчер и реестр действий."""

from __future__ import annotations

import contextvars
import logging
import re
from decimal import Decimal
from typing import Any

from models.system_settings import SystemSettingsMngr
from models.triggers import TriggerMngr
from telemetry.metrics import trigger_failures_total

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
_TRIGGER_MAX_DEPTH = 5
_trigger_depth: contextvars.ContextVar[int] = contextvars.ContextVar("trigger_depth", default=0)

_KNOWN_OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "contains", "regex"}


def _match_single(actual: Any, expected: Any) -> bool:
    """Сопоставление фактического значения контекста с ожидаемым (Triggers 2.0).

    Поддерживает:
    - Простое равенство: {"status": "paid"}
    - Словарь операторов: {"amount": {"gt": 500, "lte": 5000}}
      Доступные операторы: eq, ne, gt, gte, lt, lte, in, not_in, contains, regex.
    """
    if isinstance(expected, dict):
        # Если ни один ключ не является оператором, считаем это точным совпадением словарей
        if not any(k in _KNOWN_OPERATORS for k in expected):
            return actual == expected

        for op, target in expected.items():
            if op == "eq":
                if actual != target:
                    return False
            elif op == "ne":
                if actual == target:
                    return False
            elif op in ("gt", "gte", "lt", "lte"):
                if actual is None or target is None:
                    return False
                try:
                    # Попытка численного приведения для безопасного сравнения int/float/Decimal/str
                    act_num = Decimal(str(actual))
                    tgt_num = Decimal(str(target))
                    if op == "gt" and not (act_num > tgt_num):
                        return False
                    if op == "gte" and not (act_num >= tgt_num):
                        return False
                    if op == "lt" and not (act_num < tgt_num):
                        return False
                    if op == "lte" and not (act_num <= tgt_num):
                        return False
                except (Exception, ArithmeticError):
                    # Fallback к обычному сравнению типов
                    try:
                        if op == "gt" and not (actual > target):
                            return False
                        if op == "gte" and not (actual >= target):
                            return False
                        if op == "lt" and not (actual < target):
                            return False
                        if op == "lte" and not (actual <= target):
                            return False
                    except TypeError:
                        return False
            elif op == "in":
                if isinstance(target, (list, tuple, set)):
                    if actual not in target:
                        return False
                elif isinstance(target, str):
                    if str(actual) not in target:
                        return False
                else:
                    return False
            elif op == "not_in":
                if isinstance(target, (list, tuple, set)):
                    if actual in target:
                        return False
                elif isinstance(target, str):
                    if str(actual) in target:
                        return False
            elif op == "contains":
                if actual is None:
                    return False
                if isinstance(actual, (list, tuple, set)):
                    if target not in actual:
                        return False
                elif isinstance(actual, str):
                    if str(target) not in actual:
                        return False
                else:
                    return False
            elif op == "regex":
                if actual is None:
                    return False
                try:
                    if not re.search(str(target), str(actual)):
                        return False
                except re.error:
                    return False
        return True

    return actual == expected


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
        """Все пары ``{path: value/operators}`` условия должны совпасть с контекстом.

        :arg cond: условие триггера (поддерживает операторы Triggers 2.0).
        :arg ctx: контекст события.
        :return: ``True`` если условие выполнено (или пустое).
        """
        if not cond:
            return True
        return all(_match_single(dig(ctx, path), expected) for path, expected in cond.items())

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
        depth = _trigger_depth.get()
        if depth >= _TRIGGER_MAX_DEPTH:
            log.warning(
                "триггеры: анти-петля глубины — каскад прерван для %s (глубина %d >= %d)",
                event,
                depth,
                _TRIGGER_MAX_DEPTH,
            )
            return 0

        if not await self._allow_event(event):
            return 0

        token = _trigger_depth.set(depth + 1)
        try:
            return await self._fire_internal(event, ctx)
        finally:
            _trigger_depth.reset(token)

    async def _fire_internal(self, event: str, ctx: dict) -> int:
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
            last_error: str | None = None
            for attempt in range(1, max(1, max_retries) + 1):
                try:
                    if await action.run(event, ctx, trig.config or {}):
                        ok = True
                        break
                    last_error = "action returned false"
                except Exception as exc:  # noqa: BLE001 — триггер не ломает операцию
                    last_error = str(exc)[:512]
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
            else:
                trigger_failures_total.labels(event=event, action=trig.action).inc()
                log.error(
                    "триггер #%s (%s/%s): исчерпаны все %s попыток: %s",
                    trig.id,
                    event,
                    trig.action,
                    max_retries,
                    last_error,
                )
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
