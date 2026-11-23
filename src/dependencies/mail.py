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
from utils.mail import LuaMailSvc, MailSvc
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


async def build_mail_svc(
    settings: SystemSettingsMngr,
    cfg: AppConfig | None = None,
    bus=None,
    session=None,
) -> MailSvc | LuaMailSvc:
    """Собрать транспорт писем из настроек БД (SMTP или Lua-скрипт) с fallback на cfg.

    :arg settings: менеджер системных настроек.
    :arg cfg: глобальная конфигурация (опционально).
    :arg bus: шина LuaWorker (для Lua-драйвера).
    :arg session: сессия БД (для Lua-драйвера).
    :return: транспорт отправки писем.
    """
    mail_grp = await settings.get_group("mail.")
    driver = mail_grp.get("mail.driver") or (cfg.MAIL_DRIVER if cfg else "smtp")

    if driver == "lua":
        script_id = mail_grp.get("mail.lua_script_id") or (cfg.MAIL_LUA_SCRIPT_ID if cfg else None)
        raw_version = mail_grp.get("mail.lua_script_version") or (cfg.MAIL_LUA_SCRIPT_VERSION if cfg else None)
        script_version: int | None = None
        if raw_version is not None and str(raw_version).strip():
            ver_s = str(raw_version).strip()
            if ver_s.isdigit():
                script_version = int(ver_s)
        smtp_grp = await settings.get_group("smtp.")
        sender = smtp_grp.get("smtp.from") or (cfg.SMTP_FROM if cfg else None)
        from_name = smtp_grp.get("smtp.from_name") or (cfg.SMTP_FROM_NAME if cfg else None)
        sess = session or settings.s
        if bus and script_id and sess:
            return LuaMailSvc(
                bus=bus,
                session=sess,
                script_id=int(script_id),
                script_version=script_version,
                sender=sender,
                from_name=from_name,
            )

    grp = await settings.get_group("smtp.")

    host = grp.get("smtp.host")
    if host is None and cfg:
        host = cfg.SMTP_HOST
    port = int(grp.get("smtp.port") or (cfg.SMTP_PORT if cfg else 587))
    user = grp.get("smtp.user")
    if user is None and cfg:
        user = cfg.SMTP_USER
    password = grp.get("smtp.pass")
    if password is None and cfg:
        password = cfg.SMTP_PASS
    sender = grp.get("smtp.from")
    if sender is None and cfg:
        sender = cfg.SMTP_FROM
    from_name = grp.get("smtp.from_name")
    if from_name is None and cfg:
        from_name = cfg.SMTP_FROM_NAME
    timeout = float(grp.get("smtp.timeout") or (cfg.SMTP_TIMEOUT if cfg else 10))

    encryption = grp.get("smtp.encryption")
    if not encryption:
        tls_val = grp.get("smtp.tls")
        if tls_val is not None:
            use_tls = tls_val not in ("0", "false", "False")
            encryption = "ssl" if (use_tls and port in (465, 9465)) else ("starttls" if use_tls else "none")
        elif cfg and cfg.SMTP_ENCRYPTION:
            encryption = cfg.SMTP_ENCRYPTION
        elif cfg and not cfg.SMTP_TLS:
            encryption = "none"
        else:
            encryption = "ssl" if port in (465, 9465) else "starttls"

    return MailSvc(
        host=host,
        port=port,
        user=user,
        password=password,
        sender=sender,
        from_name=from_name,
        encryption=encryption,
        timeout=timeout,
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
    from lua.deps import get_lua_bus

    cfg: AppConfig = request.app.state.settings
    bus = get_lua_bus(request)
    mail = await build_mail_svc(settings, cfg, bus=bus, session=session)
    sender = EmailSender(mail, EmailMngr(session, cfg.EMAIL_TEMPLATES_DIR))
    return VerifySvc(session, vk, settings, sender, cfg.VERIFY_TOKEN_TTL)


__all__ = ["VerifySvc", "MailSvc", "LuaMailSvc", "build_mail_svc", "get_verify_svc"]
