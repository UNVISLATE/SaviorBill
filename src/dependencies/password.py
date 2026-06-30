"""Сброс пароля по email (одноразовый токен в Valkey + письмо по шаблону)."""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.email import get_email_sender
from dependencies.valkey import get_valkey_client
from integrations.email import EmailEvent, EmailSender
from models.user import UserModel, UserMngr
from utils.config import AppConfig
from utils.sec.crypt import generate_base_token
from utils.sec.pwd import hash_pass

# Префикс ключа токена сброса пароля в Valkey.
_RESET = "reset:pwd:"


class ResetSvc:
    """Запрос и подтверждение сброса пароля."""

    def __init__(
        self,
        session: AsyncSession,
        vk: valkey.Valkey,
        sender: EmailSender,
        public_url: str,
        ttl: int,
    ) -> None:
        self.s = session
        self.vk = vk
        self.sender = sender
        self.public_url = public_url.rstrip("/")
        self.ttl = ttl

    async def request(self, email: str) -> None:
        """Сгенерировать токен и отправить письмо со ссылкой сброса.

        Не раскрывает существование аккаунта: при отсутствии адреса/почты
        просто молча выходит (вызывающий всегда отвечает 202).
        """
        acc = await UserMngr(self.s).by_email(email)
        if acc is None or not acc.email or not acc.is_active:
            return

        token = generate_base_token()
        await self.vk.set(_RESET + token, str(acc.id), ex=self.ttl)

        link = f"{self.public_url}/api/v1/auth/password/reset/confirm?token={token}"
        ctx = {
            "user": {"id": acc.id, "login": acc.login, "email": acc.email},
            "reset_url": link,
            "token": token,
        }
        # Письмо по шаблону события password.reset (если он заведён).
        await self.sender.send_template(EmailEvent.PASSWORD_RESET, acc.email, ctx)

    async def confirm(self, token: str, new_pass: str) -> UserModel:
        """Установить новый пароль по токену сброса."""
        raw = await self.vk.get(_RESET + token)
        if raw is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "неверный или истёкший токен"
            )
        await self.vk.delete(_RESET + token)

        acc = await self.s.get(UserModel, int(raw))
        if acc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "аккаунт не найден")
        acc.pass_hash = hash_pass(new_pass)
        await self.s.flush()
        return acc


async def get_reset_svc(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    vk: valkey.Valkey = Depends(get_valkey_client),
    sender: EmailSender = Depends(get_email_sender),
) -> ResetSvc:
    cfg: AppConfig = request.app.state.settings
    return ResetSvc(session, vk, sender, cfg.PUBLIC_URL, cfg.RESET_TOKEN_TTL)


__all__ = ["ResetSvc", "get_reset_svc"]
