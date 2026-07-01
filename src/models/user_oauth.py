"""OAuth-привязка пользователя (UserOauthModel) + менеджер (UserOauthMngr)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    func,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base
from utils.datetime_utils import utc_now

if TYPE_CHECKING:
    from models.user import UserModel


class UserOauthModel(Base):
    """Привязка внешней OAuth-учётки к локальному аккаунту."""

    __tablename__ = "oauth_conns"
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_oauth_provider_subject"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # Идентификатор пользователя у провайдера (OIDC claim ``sub``).
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    account: Mapped["UserModel"] = relationship(back_populates="oauth_conns")


class UserOauthMngr:
    """CRUD для OAuth-привязок пользователей."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def by_id(self, conn_id: int) -> UserOauthModel | None:
        return await self.s.get(UserOauthModel, conn_id)

    async def by_provider_subject(
        self, provider: str, subject: str
    ) -> UserOauthModel | None:
        return await self.s.scalar(
            select(UserOauthModel).where(
                UserOauthModel.provider == provider,
                UserOauthModel.subject == subject,
            )
        )

    async def list_for_account(self, account_id: int) -> list[UserOauthModel]:
        rows = await self.s.scalars(
            select(UserOauthModel)
            .where(UserOauthModel.account_id == account_id)
            .order_by(UserOauthModel.id)
        )
        return list(rows)

    async def create(
        self,
        account_id: int,
        provider: str,
        subject: str,
        email: str | None = None,
        raw: dict | None = None,
    ) -> UserOauthModel:
        conn = UserOauthModel(
            account_id=account_id,
            provider=provider,
            subject=subject,
            email=email,
            raw=raw or {},
        )
        self.s.add(conn)
        await self.s.flush()
        return conn


__all__ = ["UserOauthModel", "UserOauthMngr"]
