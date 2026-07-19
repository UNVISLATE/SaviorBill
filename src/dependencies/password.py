"""Сброс пароля по email (код или временный токен), с настройкой способа."""

from __future__ import annotations

import hmac

import valkey.asyncio as valkey
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.email import get_email_sender
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.valkey import get_valkey_client
from notifications.email import EmailEvent, EmailSender
from models.user import UserModel, UserMngr
from utils.config import AppConfig
from security.sec.crypt import generate_base_token, generate_numeric_code
from security.sec.pwd import hash_pass

# Ключи Valkey: секрет привязан к email + счётчик неверных попыток. Для
# token-режима дополнительно хранится обратный индекс token -> email (чтобы
# подтвердить сброс по одной лишь ссылке, без явного email в теле запроса).
_RESET = "reset:pwd:"
_RESET_FAIL = "reset:pwd:fail:"
_RESET_TOKEN_IDX = "reset:pwd:tok:"
# Длина кода сброса (для режима "code") и потолок неверных попыток на код.
_CODE_DIGITS = 6
_MAX_FAILS = 5

# Способы сброса пароля (настройка ``password.reset.method``):
# - code/token   — сброс по email (числовой код либо ссылка-токен);
# - authenticated — email-сброс выключен, доступна только смена пароля в
#   профиле (`PUT /me/password`, знание текущего пароля);
# - disabled     — сброс пароля недоступен вообще ни одним из способов.
METHOD_CODE = "code"
METHOD_TOKEN = "token"
METHOD_AUTHENTICATED = "authenticated"
METHOD_DISABLED = "disabled"
_KNOWN_METHODS = frozenset(
    {METHOD_CODE, METHOD_TOKEN, METHOD_AUTHENTICATED, METHOD_DISABLED}
)


async def resolve_reset_method(settings: SystemSettingsMngr) -> str:
    """Прочитать и нормализовать настройку ``password.reset.method``.

    Неизвестное/отсутствующее значение — безопасный дефолт ``code`` (как было
    до появления настройки).
    """
    value = await settings.get("password.reset.method", METHOD_CODE)
    return value if value in _KNOWN_METHODS else METHOD_CODE


class ResetSvc:
    """Запрос и подтверждение сброса пароля по коду или временному токену."""

    def __init__(
        self,
        session: AsyncSession,
        vk: valkey.Valkey,
        settings: SystemSettingsMngr,
        sender: EmailSender,
        default_ttl: int,
    ) -> None:
        self.s = session
        self.vk = vk
        self.settings = settings
        self.sender = sender
        self.default_ttl = default_ttl

    async def _ttl(self) -> int:
        """TTL кода: тот же, что у подтверждения email (``mail.code_ttl``/ENV)."""
        return await self.settings.get_int("mail.code_ttl", self.default_ttl)

    @staticmethod
    def _norm(email: str) -> str:
        """Нормализовать email для ключа (нижний регистр, без пробелов)."""
        return email.strip().lower()

    async def request(self, email: str) -> None:
        """Сгенерировать код/токен и отправить письмо со сбросом пароля.

        Не раскрывает существование аккаунта: при отсутствии адреса/почты молча
        выходит. Но при ненастроенном SMTP или выключенном email-сбросе
        (``password.reset.method`` = ``authenticated``/``disabled``) отвечает
        404 (системное состояние, а не факт про конкретный аккаунт).

        :arg email: адрес, на который запрошен сброс.
        """
        method = await resolve_reset_method(self.settings)
        if method in (METHOD_AUTHENTICATED, METHOD_DISABLED):
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "password reset by email is disabled"
            )
        if not self.sender.configured:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "email sending is not configured"
            )

        acc = await UserMngr(self.s).by_email(self._norm(email))
        if acc is None or not acc.email or not acc.is_active:
            return

        norm = self._norm(acc.email)
        secret = (
            generate_base_token()
            if method == METHOD_TOKEN
            else generate_numeric_code(_CODE_DIGITS)
        )
        ttl = await self._ttl()
        await self.vk.set(_RESET + norm, secret, ex=ttl)
        await self.vk.delete(_RESET_FAIL + norm)
        if method == METHOD_TOKEN:
            # Обратный индекс: подтверждение по ссылке без указания email.
            await self.vk.set(_RESET_TOKEN_IDX + secret, norm, ex=ttl)

        ctx = {
            "user": {"id": acc.id, "login": acc.login, "email": acc.email},
            "code": secret if method == METHOD_CODE else None,
            "token": secret if method == METHOD_TOKEN else None,
            "ttl_minutes": max(1, ttl // 60),
        }
        sent = await self.sender.send_template(
            EmailEvent.PASSWORD_RESET, acc.email, ctx
        )
        if not sent:
            label = "token" if method == METHOD_TOKEN else "code"
            await self.sender.mail.send(
                acc.email,
                "Password reset",
                f"Your password reset {label}: {secret}",
            )

    async def confirm(
        self, code: str, new_pass: str, *, email: str | None = None
    ) -> UserModel:
        """Установить новый пароль по коду/токену сброса.

        :arg code: код (режим ``code``) или токен (режим ``token``) из письма.
        :arg new_pass: новый пароль.
        :arg email: адрес, на который запрашивался сброс. Обязателен в режиме
            ``code``; для ``token`` может быть опущен — тогда аккаунт находится
            по обратному индексу токена.
        :return: обновлённый аккаунт.
        """
        method = await resolve_reset_method(self.settings)
        if method in (METHOD_AUTHENTICATED, METHOD_DISABLED):
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "password reset by email is disabled"
            )

        norm = self._norm(email) if email else None
        if norm is None:
            norm = await self.vk.get(_RESET_TOKEN_IDX + code)
            if norm is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid code")

        key = _RESET + norm
        stored = await self.vk.get(key)
        if stored is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "code not requested or expired"
            )
        if not hmac.compare_digest(stored, code):
            fails = await self.vk.incr(_RESET_FAIL + norm)
            if fails >= _MAX_FAILS:
                await self.vk.delete(key)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid code")

        acc = await UserMngr(self.s).by_email(norm)
        if acc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")

        await self.vk.delete(key)
        await self.vk.delete(_RESET_FAIL + norm)
        await self.vk.delete(_RESET_TOKEN_IDX + code)
        acc.pass_hash = hash_pass(new_pass)
        await self.s.flush()
        return acc


async def get_reset_svc(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    vk: valkey.Valkey = Depends(get_valkey_client),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    sender: EmailSender = Depends(get_email_sender),
) -> ResetSvc:
    cfg: AppConfig = request.app.state.settings
    return ResetSvc(session, vk, settings, sender, cfg.VERIFY_TOKEN_TTL)


__all__ = [
    "ResetSvc",
    "get_reset_svc",
    "resolve_reset_method",
    "METHOD_CODE",
    "METHOD_TOKEN",
    "METHOD_AUTHENTICATED",
    "METHOD_DISABLED",
]
