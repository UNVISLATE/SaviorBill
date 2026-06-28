"""DI и сервис верификации email (через одноразовый токен в Valkey + SMTP)."""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.settings import SettingsMngr, get_settings_mngr
from dependencies.valkey import get_valkey_client
from models.user import Account
from utils.config import AppConfig
from utils.mail import MailSvc
from utils.sec.crypt import generate_base_token

# Префикс и TTL токена верификации email.
_VERIFY = "verify:email:"
_VERIFY_TTL = 3600


async def build_mail_svc(settings: SettingsMngr) -> MailSvc:
    """Собрать :class:`MailSvc` из настроек SMTP в БД."""
    grp = await settings.get_group("smtp.")
    return MailSvc(
        host=grp.get("smtp.host"),
        port=int(grp.get("smtp.port") or 587),
        user=grp.get("smtp.user"),
        password=grp.get("smtp.pass"),
        sender=grp.get("smtp.from"),
        use_tls=(grp.get("smtp.tls", "1") not in ("0", "false", "False")),
    )


class VerifySvc:
    """Верификация email пользователя одноразовым токеном."""

    def __init__(
        self,
        session: AsyncSession,
        vk: valkey.Valkey,
        settings: SettingsMngr,
        public_url: str,
    ) -> None:
        self.s = session
        self.vk = vk
        self.settings = settings
        self.public_url = public_url.rstrip("/")

    async def request_email(self, acc: Account) -> None:
        """Сгенерировать токен и отправить письмо со ссылкой подтверждения."""
        if not acc.email:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "email не задан")
        if acc.is_verified:
            raise HTTPException(status.HTTP_409_CONFLICT, "email уже подтверждён")

        token = generate_base_token()
        await self.vk.set(_VERIFY + token, str(acc.id), ex=_VERIFY_TTL)

        mail = await build_mail_svc(self.settings)
        if not mail.configured:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "отправка почты не настроена"
            )
        link = f"{self.public_url}/api/v1/user/me/verify/email/confirm?token={token}"
        await mail.send(
            acc.email,
            "Подтверждение email",
            f"Для подтверждения email перейдите по ссылке:\n{link}",
        )

    async def confirm_email(self, token: str) -> Account:
        """Подтвердить email по токену."""
        raw = await self.vk.get(_VERIFY + token)
        if raw is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "неверный или истёкший токен"
            )
        await self.vk.delete(_VERIFY + token)

        acc = await self.s.get(Account, int(raw))
        if acc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "аккаунт не найден")
        acc.is_verified = True
        await self.s.flush()
        return acc


def get_verify_svc(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    vk: valkey.Valkey = Depends(get_valkey_client),
    settings: SettingsMngr = Depends(get_settings_mngr),
) -> VerifySvc:
    cfg: AppConfig = request.app.state.settings
    return VerifySvc(session, vk, settings, cfg.PUBLIC_URL)


__all__ = ["VerifySvc", "MailSvc", "build_mail_svc", "get_verify_svc"]
