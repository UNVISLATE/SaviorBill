"""Анти-брутфорс блокировка входа: доп. слой поверх общего ``rate_limit``.

Две независимые Valkey-блокировки — по логину и по IP, — обе должны быть
ниже порога, чтобы попытка входа продолжилась. См. IMPLEMENTATION_PLAN §6.3.
"""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import Depends, HTTPException, Request, status

from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.valkey import get_valkey_client
from utils.degrade import VALKEY_ERRORS, note_degraded

_DEFAULT_MAX_ATTEMPTS = 5
_DEFAULT_WINDOW_SEC = 900  # 15 минут

_ACC_PREFIX = "login:fail:acc:"
_IP_PREFIX = "login:fail:ip:"
# Счётчик по паре логин+IP: общий IP-счётчик за офисом/NAT блокировал всех
# сразу, поэтому порог по «чистому» IP поднят множителем ниже (AUDIT.md §2.1).
_PAIR_PREFIX = "login:fail:pair:"
# Во сколько раз порог по одному лишь IP выше порога по логину.
_IP_THRESHOLD_FACTOR = 4


def client_ip(request: Request) -> str:
    """IP клиента (без доверия заголовкам прокси — см. §11 плана)."""
    return request.client.host if request.client else "unknown"


class LoginGuard:
    """Проверка/учёт неудачных попыток входа с временной блокировкой."""

    def __init__(self, vk: valkey.Valkey, settings: SystemSettingsMngr) -> None:
        self.vk = vk
        self.settings = settings

    async def _limits(self) -> tuple[int, int]:
        max_attempts = await self.settings.get_int(
            "auth.lockout.max_attempts", _DEFAULT_MAX_ATTEMPTS
        )
        window = await self.settings.get_int(
            "auth.lockout.window_sec", _DEFAULT_WINDOW_SEC
        )
        return max_attempts or _DEFAULT_MAX_ATTEMPTS, window or _DEFAULT_WINDOW_SEC

    async def check(self, login: str, ip: str) -> None:
        """Бросить 429, если логин или IP уже превысили порог попыток.

        Пароль в этом случае вовсе не проверяется — блокировка сообщает лишь
        факт "слишком много попыток", это не создаёт новой тайминг-утечки о
        существовании аккаунта (см. §6.3 плана).

        При недоступности Valkey попытка пропускается: без счётчиков блокировка
        всё равно не работает, а отказ во входе всем — хуже (пароль проверяется
        в любом случае).
        """
        acc_key, ip_key = _ACC_PREFIX + login, _IP_PREFIX + ip
        pair_key = f"{_PAIR_PREFIX}{ip}:{login}"
        try:
            max_attempts, _ = await self._limits()
            acc_n, ip_n, pair_n = await self.vk.mget([acc_key, ip_key, pair_key])
            acc_n, ip_n, pair_n = int(acc_n or 0), int(ip_n or 0), int(pair_n or 0)
            ip_limit = max_attempts * _IP_THRESHOLD_FACTOR
            if acc_n < max_attempts and pair_n < max_attempts and ip_n < ip_limit:
                return
            ttl_acc = await self.vk.ttl(acc_key)
            ttl_ip = await self.vk.ttl(ip_key)
            ttl_pair = await self.vk.ttl(pair_key)
        except VALKEY_ERRORS as exc:
            note_degraded("login_guard", exc)
            return
        retry_after = max(ttl_acc or 0, ttl_ip or 0, ttl_pair or 0, 1)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many failed login attempts, try again later",
            headers={"Retry-After": str(retry_after)},
        )

    async def record_fail(self, login: str, ip: str) -> None:
        """Учесть неудачную попытку по логину, IP и их паре."""
        try:
            _, window = await self._limits()
            keys = (
                _ACC_PREFIX + login,
                _IP_PREFIX + ip,
                f"{_PAIR_PREFIX}{ip}:{login}",
            )
            for key in keys:
                n = await self.vk.incr(key)
                if n == 1:
                    await self.vk.expire(key, window)
        except VALKEY_ERRORS as exc:
            note_degraded("login_guard", exc)

    async def clear(self, login: str, ip: str | None = None) -> None:
        """Сбросить счётчики неудач логина при успешном входе.

        Общий IP-счётчик умышленно НЕ сбрасывается — иначе атакующий, зная
        один валидный пароль, мог бы периодически "обнулять" его и продолжать
        перебор по другим логинам с того же IP. Счётчик пары логин+IP сбросить
        можно: он относится к конкретному успешно вошедшему пользователю.
        """
        try:
            await self.vk.delete(_ACC_PREFIX + login)
            if ip is not None:
                await self.vk.delete(f"{_PAIR_PREFIX}{ip}:{login}")
        except VALKEY_ERRORS as exc:
            note_degraded("login_guard", exc)


def get_login_guard(
    vk: valkey.Valkey = Depends(get_valkey_client),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> LoginGuard:
    """DI-фабрика ``LoginGuard``."""
    return LoginGuard(vk, settings)


__all__ = ["LoginGuard", "get_login_guard", "client_ip"]
