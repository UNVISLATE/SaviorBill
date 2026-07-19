"""DI и сервис верификации email (4-значный код в Valkey + SMTP)."""

from __future__ import annotations

import hmac

import valkey.asyncio as valkey
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.valkey import get_valkey_client
from lifecycle.notifications import EmailEvent, EmailSender
from models.email_templates import EmailMngr
from models.user import UserModel
from core.config import AppConfig
from utils.mail import MailSvc
from security.sec.crypt import generate_numeric_code

# Ключи Valkey: код привязан к аккаунту (verify) + счётчик неверных попыток.
_VERIFY = "verify:email:"
_VERIFY_FAIL = "verify:email:fail:"
# Длина кода подтверждения email и потолок неверных попыток на код.
# 4 цифры (10к комбинаций) — слишком короткий код для брутфорса даже с
# лимитом попыток; 6 цифр — тот же порядок, что уже
# используется для сброса пароля (dependencies/password.py::_CODE_DIGITS).
_CODE_DIGITS = 6
_MAX_FAILS = 5


def _const_eq(a: str, b: str) -> bool:
    """Сравнить строки за постоянное время (анти-тайминг).

    :arg a: первая строка; :arg b: вторая строка.
    :return: ``True`` если строки равны.
    """
    return hmac.compare_digest(a, b)


async def build_mail_svc(settings: SystemSettingsMngr) -> MailSvc:
    """Собрать транспорт писем из настроек SMTP в БД.

    :arg settings: менеджер системных настроек.
    :return: транспорт отправки писем (может быть не сконфигурирован).
    """
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
    """Верификация email пользователя одноразовым числовым кодом."""

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
        """TTL кода: настройка ``mail.code_ttl`` из БД, иначе значение ENV."""
        return await self.settings.get_int("mail.code_ttl", self.default_ttl)

    async def _digits(self) -> int:
        """Длина кода: настройка ``mail.code_digits`` из БД, иначе дефолт."""
        return await self.settings.get_int("mail.code_digits", _CODE_DIGITS) or (
            _CODE_DIGITS
        )

    async def request_email(self, acc: UserModel) -> None:
        """Сгенерировать код и отправить письмо с кодом подтверждения email.

        :arg acc: аккаунт, запросивший подтверждение email.
        """
        if not acc.email:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "email not set")
        if acc.is_verified:
            raise HTTPException(status.HTTP_409_CONFLICT, "email already verified")
        if not self.sender.configured:
            # По требованию: отсутствие настроенного SMTP — 404 с пояснением.
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "email sending is not configured"
            )

        code = generate_numeric_code(await self._digits())
        ttl = await self._ttl()
        await self.vk.set(_VERIFY + str(acc.id), code, ex=ttl)
        await self.vk.delete(_VERIFY_FAIL + str(acc.id))

        ctx = {
            "user": {"id": acc.id, "login": acc.login, "email": acc.email},
            "code": code,
            "ttl_minutes": max(1, ttl // 60),
        }
        sent = await self.sender.send_template(EmailEvent.EMAIL_VERIFY, acc.email, ctx)
        if not sent:
            await self.sender.mail.send(
                acc.email,
                "Подтверждение email",
                f"Код подтверждения email: {code}",
            )

    async def confirm_email(self, acc: UserModel, code: str) -> UserModel:
        """Подтвердить email по числовому коду.

        :arg acc: текущий аутентифицированный аккаунт.
        :arg code: код из письма (длина настраивается через ``mail.code_digits``).
        :return: обновлённый аккаунт (``is_verified=True``).
        """
        if acc.is_verified:
            raise HTTPException(status.HTTP_409_CONFLICT, "email already verified")

        key = _VERIFY + str(acc.id)
        stored = await self.vk.get(key)
        if stored is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "code not requested or expired"
            )
        if not _const_eq(stored, code):
            fails = await self.vk.incr(_VERIFY_FAIL + str(acc.id))
            if fails >= _MAX_FAILS:
                await self.vk.delete(key)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid code")

        await self.vk.delete(key)
        await self.vk.delete(_VERIFY_FAIL + str(acc.id))
        # Верификация = смена роли guest -> user (производный is_verified=True).
        from models.user import UserMngr
        from enums import BaseRole

        await UserMngr(self.s).set_role_key(acc, BaseRole.USER)
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
    return VerifySvc(session, vk, settings, sender, cfg.VERIFY_TOKEN_TTL)


__all__ = ["VerifySvc", "MailSvc", "build_mail_svc", "get_verify_svc"]
