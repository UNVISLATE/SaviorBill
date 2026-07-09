"""Аудит-таблица финансовых и административных действий (append-only)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from utils.datetime_utils import utc_now


class AuditLogModel(Base):
    """Неизменяемый журнал финансовых и административных действий."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    actor_account_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    actor_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}", nullable=False
    )
    result: Mapped[str] = mapped_column(String(16), default="ok", nullable=False)


__all__ = ["AuditLogModel"]
