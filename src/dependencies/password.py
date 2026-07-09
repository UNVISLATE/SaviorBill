"""Сброс пароля по email (6-значный код в Valkey + письмо)."""

from __future__ import annotations

import hmac

import valkey.asyncio as valkey
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.email import get_email_sender
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.valkey import get_valkey_client
from integrations.email import EmailEvent, EmailSender
from models.user import UserModel, UserMngr
from utils.config import AppConfig
from utils.sec.crypt import generate_numeric_code
from utils.sec.pwd import hash_pass

# Ключи Valkey: код привязан к email + счётчик неверных попыток.
_RESET = "reset:pwd:"
_RESET_FAIL = "reset:pwd:fail:"
# Длина кода сброса и потолок неверных попыток на код.
_CODE_DIGITS = 6
_MAX_FAILS = 5


class ResetSvc:
    """Запрос и подтверждение сброса пароля по числовому коду."""

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
        """Сгенерировать код и отправить письмо со сбросом пароля.

        Не раскрывает существование аккаунта: при отсутствии адреса/почты молча
        выходит. Но при ненастроенном SMTP отвечает 404 (системное состояние).

        :arg email: адрес, на который запрошен сброс.
        """
        if not self.sender.configured:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "email sending is not configured"
            )

        acc = await UserMngr(self.s).by_email(self._norm(email))
        if acc is None or not acc.email or not acc.is_active:
            return

        code = generate_numeric_code(_CODE_DIGITS)
        ttl = await self._ttl()
        await self.vk.set(_RESET + self._norm(acc.email), code, ex=ttl)
        await self.vk.delete(_RESET_FAIL + self._norm(acc.email))

        ctx = {
            "user": {"id": acc.id, "login": acc.login, "email": acc.email},
            "code": code,
            "ttl_minutes": max(1, ttl // 60),
        }
        sent = await self.sender.send_template(
            EmailEvent.PASSWORD_RESET, acc.email, ctx
        )
        if not sent:
            await self.sender.mail.send(
                acc.email,
                "Сброс пароля",
                f"Код для сброса пароля: {code}",
            )

    async def confirm(self, email: str, code: str, new_pass: str) -> UserModel:
        """Установить новый пароль по email + коду сброса.

        :arg email: адрес, на который запрашивался сброс.
        :arg code: 6-значный код из письма.
        :arg new_pass: новый пароль.
        :return: обновлённый аккаунт.
        """
        norm = self._norm(email)
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


__all__ = ["ResetSvc", "get_reset_svc"]
