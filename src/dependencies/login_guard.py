"""Анти-брутфорс блокировка входа: доп. слой поверх общего ``rate_limit``.

Две независимые Valkey-блокировки — по логину и по IP, — обе должны быть
ниже порога, чтобы попытка входа продолжилась. См. IMPLEMENTATION_PLAN §6.3.
"""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import Depends, HTTPException, Request, status

from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.valkey import get_valkey_client

_DEFAULT_MAX_ATTEMPTS = 5
_DEFAULT_WINDOW_SEC = 900  # 15 минут

_ACC_PREFIX = "login:fail:acc:"
_IP_PREFIX = "login:fail:ip:"


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
        """
        max_attempts, _ = await self._limits()
        acc_key, ip_key = _ACC_PREFIX + login, _IP_PREFIX + ip
        acc_n, ip_n = await self.vk.mget([acc_key, ip_key])
        acc_n, ip_n = int(acc_n or 0), int(ip_n or 0)
        if acc_n >= max_attempts or ip_n >= max_attempts:
            ttl_acc = await self.vk.ttl(acc_key)
            ttl_ip = await self.vk.ttl(ip_key)
            retry_after = max(ttl_acc or 0, ttl_ip or 0, 1)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail="слишком много неудачных попыток входа, попробуйте позже",
                headers={"Retry-After": str(retry_after)},
            )

    async def record_fail(self, login: str, ip: str) -> None:
        """Учесть неудачную попытку по обоим ключам (логин + IP)."""
        _, window = await self._limits()
        for key in (_ACC_PREFIX + login, _IP_PREFIX + ip):
            n = await self.vk.incr(key)
            if n == 1:
                await self.vk.expire(key, window)

    async def clear(self, login: str) -> None:
        """Сбросить счётчик неудач конкретного логина при успешном входе.

        IP-счётчик умышленно НЕ сбрасывается — иначе атакующий, зная один
        валидный пароль, мог бы периодически "обнулять" IP-счётчик и
        продолжать перебор по другим логинам с того же IP.
        """
        await self.vk.delete(_ACC_PREFIX + login)


def get_login_guard(
    vk: valkey.Valkey = Depends(get_valkey_client),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> LoginGuard:
    """DI-фабрика ``LoginGuard``."""
    return LoginGuard(vk, settings)


__all__ = ["LoginGuard", "get_login_guard", "client_ip"]
