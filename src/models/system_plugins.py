"""Реестр бандлов плагинов ядра в БД (для мульти-серверного кластера без NFS)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, LargeBinary, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from utils.datetime_utils import utc_now


class SystemPluginModel(Base):
    """Запись о бандле плагина (UI + Python-код) для синхронизации между нодами."""

    __tablename__ = "system_plugins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bundle_backend: Mapped[str] = mapped_column(
        String(16), default="fs", server_default="fs", nullable=False
    )
    bundle_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bundle_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
        nullable=False,
    )


__all__ = ["SystemPluginModel"]
