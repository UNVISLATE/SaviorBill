"""Админ: управление настройками почтового транспорта (SMTP / Lua) (/api/v1/admin/settings/smtp)."""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

import aiosmtplib
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import AppConfig
from dependencies.db import get_db_session
from dependencies.mail import build_mail_svc
from dependencies.rbac import require_perm
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from lua.deps import get_lua_bus
from schemas.types import NormEmail
from services.audit import audit

log = logging.getLogger("saviorbill.settings.smtp")

router = APIRouter()


class SmtpSettingsOut(BaseModel):
    driver: Literal["smtp", "lua"] = "smtp"
    lua_script_id: int | None = None
    lua_script_version: str | None = None

    # SMTP fields
    host: str | None = None
    port: int = 587
    user: str | None = None
    has_password: bool = False
    from_email: str | None = None
    from_name: str | None = None
    encryption: Literal["starttls", "ssl", "none"] = "starttls"
    timeout: int = 10
    use_tls: bool = True
    configured: bool = False


class SmtpSettingsIn(BaseModel):
    driver: Literal["smtp", "lua"] = Field(default="smtp", description="Почтовый транспорт: smtp или lua")
    lua_script_id: int | None = Field(default=None, description="ID Lua-скрипта почтового транспорта (при driver=lua)")
    lua_script_version: str | None = Field(default=None, description="Версия Lua-скрипта почтового транспорта")

    # SMTP fields
    host: str | None = Field(default=None, description="SMTP host (domain or IP)")
    port: int = Field(default=587, ge=1, le=65535, description="SMTP port (any port, e.g. 587, 465, 9465, 9587, 2525)")
    user: str | None = Field(default=None, description="SMTP username / login")
    password: str | None = Field(default=None, description="New SMTP password (leave empty to keep unchanged)")
    clear_password: bool = Field(default=False, description="Clear existing saved password")
    from_email: str | None = Field(default=None, description="Sender email address (From)")
    from_name: str | None = Field(default=None, description="Sender display name (From Name, optional)")
    encryption: Literal["starttls", "ssl", "none"] = Field(
        default="starttls",
        description="Encryption mode: starttls (STARTTLS), ssl (Direct TLS/SSL), none (Plain text)",
    )
    timeout: int = Field(default=10, ge=1, le=120, description="Connection timeout in seconds")


class SmtpTestIn(BaseModel):
    to_email: NormEmail = Field(description="Recipient email address for test message")
    from_email: str | None = Field(default=None, description="Optional sender email override (From)")
    from_name: str | None = Field(default=None, description="Optional sender display name override")


@router.get(
    "",
    response_model=SmtpSettingsOut,
    dependencies=[Depends(require_perm("settings.read"))],
    summary="Get mail / SMTP settings",
)
async def get_smtp_settings(
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> SmtpSettingsOut:
    mail_grp = await settings.get_group("mail.")
    driver = mail_grp.get("mail.driver") or "smtp"
    lua_script_id_raw = mail_grp.get("mail.lua_script_id")
    lua_script_id = int(lua_script_id_raw) if lua_script_id_raw else None
    lua_script_version = mail_grp.get("mail.lua_script_version")

    grp = await settings.get_group("smtp.")
    host = grp.get("smtp.host")
    port_val = int(grp.get("smtp.port") or 587)
    user = grp.get("smtp.user")
    has_pwd = bool(grp.get("smtp.pass"))
    from_email = grp.get("smtp.from")
    from_name = grp.get("smtp.from_name")
    timeout = int(grp.get("smtp.timeout") or 10)

    enc = grp.get("smtp.encryption")
    if not enc:
        tls_val = grp.get("smtp.tls", "1")
        use_tls = tls_val not in ("0", "false", "False")
        enc = "ssl" if (use_tls and port_val in (465, 9465)) else ("starttls" if use_tls else "none")
    elif enc not in ("starttls", "ssl", "none"):
        enc = "starttls"

    if driver == "lua":
        configured = bool(lua_script_id)
    else:
        configured = bool(host and from_email)

    return SmtpSettingsOut(
        driver=driver if driver in ("smtp", "lua") else "smtp",
        lua_script_id=lua_script_id,
        lua_script_version=lua_script_version,
        host=host,
        port=port_val,
        user=user,
        has_password=has_pwd,
        from_email=from_email,
        from_name=from_name,
        encryption=enc,
        timeout=timeout,
        use_tls=enc != "none",
        configured=configured,
    )


@router.post(
    "",
    dependencies=[Depends(require_perm("settings.edit"))],
    summary="Update mail / SMTP settings",
)
async def update_smtp_settings(
    body: SmtpSettingsIn,
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> dict:
    await settings.set("mail.driver", body.driver)
    await settings.set("mail.lua_script_id", str(body.lua_script_id) if body.lua_script_id else None)
    await settings.set("mail.lua_script_version", body.lua_script_version.strip() if body.lua_script_version else None)

    host_clean = body.host.strip() if body.host else None
    user_clean = body.user.strip() if body.user else None
    from_clean = body.from_email.strip() if body.from_email else None
    from_name_clean = body.from_name.strip() if body.from_name else None

    await settings.set("smtp.host", host_clean)
    await settings.set("smtp.port", str(body.port))
    await settings.set("smtp.user", user_clean)

    if body.clear_password:
        await settings.set("smtp.pass", None)
    elif body.password is not None and body.password != "":
        await settings.set("smtp.pass", body.password)

    await settings.set("smtp.from", from_clean)
    await settings.set("smtp.from_name", from_name_clean)
    await settings.set("smtp.encryption", body.encryption)
    await settings.set("smtp.tls", "0" if body.encryption == "none" else "1")
    await settings.set("smtp.timeout", str(body.timeout))

    await audit(
        settings.s,
        action="settings_smtp_update",
        target_type="settings",
        target_id="smtp",
        meta={
            "driver": body.driver,
            "lua_script_id": body.lua_script_id,
            "host": host_clean,
            "port": body.port,
            "user": user_clean,
            "from": from_clean,
            "encryption": body.encryption,
            "timeout": body.timeout,
        },
    )
    await settings.s.commit()
    return {"ok": True}


@router.delete(
    "",
    dependencies=[Depends(require_perm("settings.edit"))],
    summary="Reset / clear mail / SMTP settings",
)
async def delete_smtp_settings(
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> dict:
    for key in (
        "mail.driver",
        "mail.lua_script_id",
        "mail.lua_script_version",
        "smtp.host",
        "smtp.port",
        "smtp.user",
        "smtp.pass",
        "smtp.from",
        "smtp.from_name",
        "smtp.encryption",
        "smtp.tls",
        "smtp.timeout",
    ):
        await settings.set(key, None)

    await audit(
        settings.s,
        action="settings_smtp_delete",
        target_type="settings",
        target_id="smtp",
        meta={"cleared": True},
    )
    await settings.s.commit()
    return {"ok": True}


@router.post(
    "/test",
    dependencies=[Depends(require_perm("settings.edit"))],
    summary="Send test email via configured transport",
)
async def send_test_email(
    body: SmtpTestIn,
    request: Request,
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    cfg: AppConfig = request.app.state.settings
    bus = get_lua_bus(request)
    mail_svc = await build_mail_svc(settings, cfg, bus=bus, session=session)

    if not mail_svc.configured:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Mail transport is not configured: configure SMTP credentials or select an active Lua transport script",
        )

    subject = "Тестовое письмо от SaviorBill"
    content = (
        "Это тестовое сообщение для проверки настроек почтового транспорта SaviorBill.\n"
        "Если вы видите это письмо, значит транспорт настроен корректно и готов к отправке писем!"
    )
    try:
        await mail_svc.send(
            body.to_email,
            subject,
            content,
            sender_override=body.from_email,
            from_name_override=body.from_name,
        )
    except aiosmtplib.errors.SMTPAuthenticationError as exc:
        host = getattr(mail_svc, "host", "smtp")
        port = getattr(mail_svc, "port", 587)
        log.warning("SMTP auth failed for %s:%s: %s", host, port, exc)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"SMTP authentication failed: invalid username or password ({exc.message or exc})",
        )
    except aiosmtplib.errors.SMTPConnectError as exc:
        host = getattr(mail_svc, "host", "smtp")
        port = getattr(mail_svc, "port", 587)
        log.warning("SMTP connect failed to %s:%s: %s", host, port, exc)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Failed to connect to SMTP server {host}:{port}: {exc.message or exc}",
        )
    except (TimeoutError, asyncio.TimeoutError) as exc:
        host = getattr(mail_svc, "host", "smtp")
        port = getattr(mail_svc, "port", 587)
        timeout = getattr(mail_svc, "timeout", 10)
        log.warning("SMTP timeout (%ss) connecting to %s:%s", timeout, host, port)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"SMTP connection timeout ({timeout}s) connecting to {host}:{port}. "
            f"Check if port is open and matches the encryption mode (STARTTLS vs SSL).",
        )
    except Exception as exc:
        log.exception("Mail test send failed: %s", exc)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Failed to send email: {exc}",
        )

    return {"ok": True, "message": f"Тестовое письмо успешно отправлено на {body.to_email}"}


__all__ = ["router"]
