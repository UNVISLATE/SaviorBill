"""Лог обращений к API (самоочищающаяся таблица)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from orm.mixins import LimitMixin
from utils.datetime_utils import utc_now


class ApiLog(LimitMixin, Base):
    """Запись лога API. Старые строки подрезаются ``ApiLog.trim()``."""

    __tablename__ = "api_logs"
    __row_limit__ = 1_000_000

    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    action: Mapped[str] = mapped_column(String(100), nullable=False)
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


__all__ = ["ApiLog"]