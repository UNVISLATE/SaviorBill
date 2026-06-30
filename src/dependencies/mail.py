"""DI и сервис верификации email (через одноразовый токен в Valkey + SMTP)."""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.valkey import get_valkey_client
from integrations.email import EmailEvent, EmailSender
from models.email_templates import EmailMngr
from models.user import UserModel
from utils.config import AppConfig
from utils.mail import MailSvc
from utils.sec.crypt import generate_base_token

# Префикс и TTL токена верификации email.
_VERIFY = "verify:email:"
_VERIFY_TTL = 3600


async def build_mail_svc(settings: SystemSettingsMngr) -> MailSvc:
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
        settings: SystemSettingsMngr,
        public_url: str,
        sender: EmailSender,
    ) -> None:
        self.s = session
        self.vk = vk
        self.settings = settings
        self.public_url = public_url.rstrip("/")
        self.sender = sender

    async def request_email(self, acc: UserModel) -> None:
        """Сгенерировать токен и отправить письмо со ссылкой подтверждения.

        Используется шаблон события ``email.verify`` (если заведён в БД); иначе
        отправляется простой текстовый fallback.
        """
        if not acc.email:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "email не задан")
        if acc.is_verified:
            raise HTTPException(status.HTTP_409_CONFLICT, "email уже подтверждён")

        if not self.sender.configured:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "отправка почты не настроена"
            )

        token = generate_base_token()
        await self.vk.set(_VERIFY + token, str(acc.id), ex=_VERIFY_TTL)

        link = f"{self.public_url}/api/v1/user/me/verify/email/confirm?token={token}"
        ctx = {
            "user": {"id": acc.id, "login": acc.login, "email": acc.email},
            "verify_url": link,
            "token": token,
        }
        sent = await self.sender.send_template(EmailEvent.EMAIL_VERIFY, acc.email, ctx)
        if not sent:
            # Шаблон не заведён — простой текстовый fallback.
            await self.sender.mail.send(
                acc.email,
                "Подтверждение email",
                f"Для подтверждения email перейдите по ссылке:\n{link}",
            )

    async def confirm_email(self, token: str) -> UserModel:
        """Подтвердить email по токену."""
        raw = await self.vk.get(_VERIFY + token)
        if raw is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "неверный или истёкший токен"
            )
        await self.vk.delete(_VERIFY + token)

        acc = await self.s.get(UserModel, int(raw))
        if acc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "аккаунт не найден")
        acc.is_verified = True
        await self.s.flush()
        return acc


async def get_verify_svc(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    vk: valkey.Valkey = Depends(get_valkey_client),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> VerifySvc:
    cfg: AppConfig = request.app.state.settings
    mail = await build_mail_svc(settings)
    sender = EmailSender(mail, EmailMngr(session, cfg.EMAIL_TEMPLATES_DIR))
    return VerifySvc(session, vk, settings, cfg.PUBLIC_URL, sender)


__all__ = ["VerifySvc", "MailSvc", "build_mail_svc", "get_verify_svc"]
