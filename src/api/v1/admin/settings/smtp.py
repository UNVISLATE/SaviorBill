"""Админ: управление настройками почтового сервера SMTP (/api/v1/admin/settings/smtp)."""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from dependencies.rbac import require_perm
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.mail import build_mail_svc
from schemas.types import NormEmail
from services.audit import audit

log = logging.getLogger("saviorbill.settings.smtp")

router = APIRouter()


class SmtpSettingsOut(BaseModel):
    host: str | None = None
    port: int = 587
    user: str | None = None
    has_password: bool = False
    from_email: str | None = None
    use_tls: bool = True


class SmtpSettingsIn(BaseModel):
    host: str | None = Field(default=None, description="SMTP хост")
    port: int = Field(default=587, ge=1, le=65535, description="SMTP порт (обычно 587 или 465)")
    user: str | None = Field(default=None, description="SMTP логин")
    password: str | None = Field(default=None, description="Новый SMTP пароль (оставьте пустым, чтобы не менять)")
    from_email: str | None = Field(default=None, description="Email отправителя (From)")
    use_tls: bool = Field(default=True, description="Использовать TLS / STARTTLS")


class SmtpTestIn(BaseModel):
    to_email: NormEmail = Field(description="Email получателя тестового письма")


@router.get(
    "",
    response_model=SmtpSettingsOut,
    dependencies=[Depends(require_perm("settings.read"))],
    summary="Get SMTP settings",
)
async def get_smtp_settings(
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> SmtpSettingsOut:
    grp = await settings.get_group("smtp.")
    host = grp.get("smtp.host")
    port_val = int(grp.get("smtp.port") or 587)
    user = grp.get("smtp.user")
    has_pwd = bool(grp.get("smtp.pass"))
    from_email = grp.get("smtp.from")
    use_tls = grp.get("smtp.tls", "1") not in ("0", "false", "False")

    return SmtpSettingsOut(
        host=host,
        port=port_val,
        user=user,
        has_password=has_pwd,
        from_email=from_email,
        use_tls=use_tls,
    )


@router.post(
    "",
    dependencies=[Depends(require_perm("settings.edit"))],
    summary="Update SMTP settings",
)
async def update_smtp_settings(
    body: SmtpSettingsIn,
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> dict:
    if body.host is not None:
        await settings.set("smtp.host", body.host.strip() if body.host else None)
    await settings.set("smtp.port", str(body.port))
    if body.user is not None:
        await settings.set("smtp.user", body.user.strip() if body.user else None)
    if body.password is not None and body.password != "":
        await settings.set("smtp.pass", body.password)
    if body.from_email is not None:
        await settings.set("smtp.from", body.from_email.strip() if body.from_email else None)
    await settings.set("smtp.tls", "1" if body.use_tls else "0")

    await audit(
        settings.s,
        action="settings_smtp_update",
        target_type="settings",
        target_id="smtp",
        meta={"host": body.host, "port": body.port, "user": body.user, "from": body.from_email},
    )
    await settings.s.commit()
    return {"ok": True}


@router.post(
    "/test",
    dependencies=[Depends(require_perm("settings.edit"))],
    summary="Send test email via SMTP",
)
async def test_smtp_connection(
    body: SmtpTestIn,
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> dict:
    mail_svc = await build_mail_svc(settings)
    if not mail_svc.configured:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "SMTP сервер не настроен: укажите хост и адрес отправителя",
        )

    subject = "Тестовое письмо от SaviorBill"
    content = (
        "Это тестовое сообщение для проверки настроек почтового сервера SMTP.\n"
        "Если вы видите это письмо, значит SMTP настроен корректно и готов к отправке писем!"
    )
    try:
        await mail_svc.send(body.to_email, subject, content)
    except Exception as exc:
        log.exception("Ошибка отправки тестового письма через SMTP: %s", exc)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Не удалось отправить письмо: {exc}",
        )

    return {"ok": True, "message": f"Тестовое письмо успешно отправлено на {body.to_email}"}


__all__ = ["router"]
