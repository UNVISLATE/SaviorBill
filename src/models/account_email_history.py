"""История email-адресов аккаунта (AccountEmailHistoryModel + менеджер)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from utils.datetime_utils import utc_now

if TYPE_CHECKING:
    from models.user import UserModel


class AccountEmailHistoryModel(Base):
    """История смены и подтверждения email-адресов пользователя."""

    __tablename__ = "account_email_history"
    __table_args__ = (
        Index("ix_account_email_history_acc_created", "account_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_initial_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    source: Mapped[str] = mapped_column(
        String(32), default="profile", server_default="profile", nullable=False
    )


class AccountEmailHistoryMngr:
    """Менеджер истории email-адресов и политики первой подтверждённой почты."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def has_initial_verified(self, account_id: int) -> bool:
        existing = await self.s.scalar(
            select(AccountEmailHistoryModel.id)
            .where(
                AccountEmailHistoryModel.account_id == account_id,
                AccountEmailHistoryModel.is_initial_verified.is_(True),
            )
            .limit(1)
        )
        return existing is not None

    async def record_email(
        self,
        account_id: int,
        email: str | None,
        *,
        verified_at: datetime | None = None,
        source: str = "profile",
    ) -> AccountEmailHistoryModel | None:
        if not email:
            return None
        norm = email.strip().lower()
        if not norm:
            return None
        is_initial = False
        if verified_at is not None and not await self.has_initial_verified(account_id):
            is_initial = True
        row = AccountEmailHistoryModel(
            account_id=account_id,
            email=norm,
            verified_at=verified_at,
            is_initial_verified=is_initial,
            source=source,
        )
        self.s.add(row)
        await self.s.flush()
        return row

    async def mark_verified(
        self,
        account_id: int,
        email: str | None,
        when: datetime | None = None,
        *,
        source: str = "verify",
    ) -> AccountEmailHistoryModel | None:
        if not email:
            return None
        norm = email.strip().lower()
        if not norm:
            return None
        ts = when or utc_now()
        row = await self.s.scalar(
            select(AccountEmailHistoryModel)
            .where(
                AccountEmailHistoryModel.account_id == account_id,
                func.lower(AccountEmailHistoryModel.email) == norm,
            )
            .order_by(AccountEmailHistoryModel.id.desc())
            .limit(1)
        )
        has_initial = await self.has_initial_verified(account_id)
        if row is None:
            row = AccountEmailHistoryModel(
                account_id=account_id,
                email=norm,
                verified_at=ts,
                is_initial_verified=not has_initial,
                source=source,
            )
            self.s.add(row)
        else:
            if row.verified_at is None:
                row.verified_at = ts
            if not has_initial:
                row.is_initial_verified = True
        await self.s.flush()
        return row

    async def first_verified_email(self, account_id: int) -> str | None:
        initial = await self.s.scalar(
            select(AccountEmailHistoryModel.email)
            .where(
                AccountEmailHistoryModel.account_id == account_id,
                AccountEmailHistoryModel.is_initial_verified.is_(True),
            )
            .order_by(AccountEmailHistoryModel.id.asc())
            .limit(1)
        )
        if initial:
            return initial
        return await self.s.scalar(
            select(AccountEmailHistoryModel.email)
            .where(
                AccountEmailHistoryModel.account_id == account_id,
                AccountEmailHistoryModel.verified_at.is_not(None),
            )
            .order_by(
                AccountEmailHistoryModel.verified_at.asc(),
                AccountEmailHistoryModel.id.asc(),
            )
            .limit(1)
        )

    async def list_for_account(self, account_id: int) -> list[AccountEmailHistoryModel]:
        rows = (
            await self.s.scalars(
                select(AccountEmailHistoryModel)
                .where(AccountEmailHistoryModel.account_id == account_id)
                .order_by(AccountEmailHistoryModel.created_at.desc(), AccountEmailHistoryModel.id.desc())
            )
        ).all()
        return list(rows)

    async def resolve_security_email(
        self, acc: "UserModel", settings
    ) -> str | None:  # noqa: ANN001
        """Вернуть адрес для критичных писем (сброс 2FA / пароля).

        Если включено ``auth.security_mail.first_verified_only``, возвращает
        первую подтверждённую почту из истории (или текущую, если она уже
        подтверждена и истории ещё нет).
        """
        first_only = await settings.get_bool(
            "auth.security_mail.first_verified_only", False
        )
        if first_only:
            first = await self.first_verified_email(acc.id)
            if first:
                return first
            if getattr(acc, "email_verified_at", None) is not None and acc.email:
                return acc.email
            return None
        if getattr(acc, "email_verified_at", None) is not None and acc.email:
            return acc.email
        if getattr(acc, "is_verified", False) and acc.email:
            return acc.email
        return None


__all__ = ["AccountEmailHistoryModel", "AccountEmailHistoryMngr"]
