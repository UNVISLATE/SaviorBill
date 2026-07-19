"""Сидинг дефолтных email-шаблонов при первом запуске.

Создаёт простые шаблоны подтверждения email и сброса пароля, если они ещё не
заведены. Тело — jinja2; в контексте доступны ``user.login``, ``code``,
``token`` (для сброса пароля в режиме ссылки, см. ``password.reset.method``)
и ``ttl_minutes``.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from notifications.email import EmailEvent
from models.email_templates import EmailMngr
from schemas.email import EmailTemplateUpload
from core.config import AppConfig

log = logging.getLogger("saviorbill.init")

# Дефолтные шаблоны: slug -> (имя, тема, тело, описание).
_DEFAULTS: tuple[tuple[str, str, str, str], ...] = (
    (
        EmailEvent.EMAIL_VERIFY,
        "Подтверждение email",
        "Код подтверждения email: {{ code }}",
        """<p>Здравствуйте, {{ user.login }}!</p>
<p>Ваш код подтверждения email:</p>
<p style="font-size:24px;font-weight:bold;letter-spacing:3px">{{ code }}</p>
<p>Код действует {{ ttl_minutes }} мин. Если вы не запрашивали подтверждение —
просто игнорируйте это письмо.</p>""",
        "Письмо с кодом подтверждения email (системное).",
    ),
    (
        EmailEvent.PASSWORD_RESET,
        "Сброс пароля",
        "Сброс пароля",
        """<p>Здравствуйте, {{ user.login }}!</p>
<p>Вы запросили сброс пароля.</p>
{% if token %}
<p>Перейдите по ссылке для смены пароля (или используйте токен вручную):</p>
<p style="font-size:14px;font-weight:bold;word-break:break-all">{{ token }}</p>
{% else %}
<p>Код для подтверждения:</p>
<p style="font-size:24px;font-weight:bold;letter-spacing:3px">{{ code }}</p>
{% endif %}
<p>Действует {{ ttl_minutes }} мин. Если вы не запрашивали сброс — никаких
действий не требуется, пароль останется прежним.</p>""",
        "Письмо с кодом/токеном сброса пароля (системное). Способ сброса "
        "определяется настройкой `password.reset.method` (code|token).",
    ),
)


async def seed_email_templates(session: AsyncSession, cfg: AppConfig) -> list[str]:
    """Создать отсутствующие дефолтные шаблоны писем. Идемпотентно.

    :param session: активная сессия БД.
    :param cfg: конфигурация приложения (путь к папке шаблонов).
    :return: список созданных слагов.
    """
    mngr = EmailMngr(session, cfg.EMAIL_TEMPLATES_DIR)
    created: list[str] = []
    for slug, name, subject, body, desc in _DEFAULTS:
        if await mngr.by_slug(slug) is not None:
            continue
        await mngr.create(
            EmailTemplateUpload(
                slug=slug,
                name=name,
                subject=subject,
                body=body,
                is_html=True,
                description=desc,
            )
        )
        created.append(slug)
    if created:
        log.info("created default email-templates: %s", ", ".join(created))
    return created


__all__ = ["seed_email_templates"]
