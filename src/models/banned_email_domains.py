"""Запрещённые для регистрации email-домены (антиспам/антифрод список).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from utils.datetime_utils import utc_now


class BannedEmailDomainModel(Base):
    """Один запрещённый для регистрации домен email (без учёта регистра)."""

    __tablename__ = "banned_email_domains"

    domain: Mapped[str] = mapped_column(String(255), primary_key=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )


class BannedEmailDomainsMngr:
    """CRUD + проверка запрещённых доменов email."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    @staticmethod
    def _domain_of(email: str) -> str:
        return email.rsplit("@", 1)[-1].strip().lower()

    async def is_banned(self, email: str) -> bool:
        """Запрещён ли домен адреса ``email`` для регистрации."""
        domain = self._domain_of(email)
        if not domain:
            return False
        row = await self.s.get(BannedEmailDomainModel, domain)
        return row is not None

    async def list_all(self) -> list[BannedEmailDomainModel]:
        rows = await self.s.scalars(
            select(BannedEmailDomainModel).order_by(BannedEmailDomainModel.domain)
        )
        return list(rows)

    async def add(
        self, domain: str, reason: str | None = None
    ) -> BannedEmailDomainModel:
        domain = domain.strip().lower()
        row = await self.s.get(BannedEmailDomainModel, domain)
        if row is None:
            row = BannedEmailDomainModel(domain=domain, reason=reason)
            self.s.add(row)
        else:
            row.reason = reason
        await self.s.flush()
        return row

    async def remove(self, domain: str) -> bool:
        row = await self.s.get(BannedEmailDomainModel, domain.strip().lower())
        if row is None:
            return False
        await self.s.delete(row)
        await self.s.flush()
        return True


__all__ = ["BannedEmailDomainModel", "BannedEmailDomainsMngr"]
