"""Учётная запись пользователя (UserModel) + менеджер (UserMngr)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    func,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base
from models.roles import Role
from enums import BaseRole
from utils.datetime_utils import utc_now

if TYPE_CHECKING:
    from models.user_oauth import UserOauthModel
    from models.roles import Role


class UserModel(Base):
    """Учётная запись"""

    __tablename__ = "accounts"

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

    login: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    email: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    pass_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), server_default="0", nullable=False
    )
    bonus_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), server_default="0", nullable=False
    )

    role_id: Mapped[int | None] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    role: Mapped["Role | None"] = relationship(back_populates="accounts", lazy="joined")
    oauth_conns: Mapped[list["UserOauthModel"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )

    @property
    def has_pass(self) -> bool:
        return self.pass_hash is not None

    @property
    def is_active(self) -> bool:
        """Активен, если роль не является заблокированной (``banned``).

        Производный флаг (роль — единственный источник истины). Отсутствие роли
        трактуется как активный пользователь.
        """
        return not (self.role is not None and self.role.key == BaseRole.BANNED)

    @property
    def is_verified(self) -> bool:
        """Верифицирован, если роль не ``guest`` и роль задана.

        ``guest`` — только что зарегистрированный пользователь (email не
        подтверждён); подтверждение переводит его в роль ``user``.
        """
        return self.role is not None and self.role.key != BaseRole.GUEST


class UserMngr:
    """Менеджер аккаунтов (тонкий слой доступа к данным)."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def by_id(self, acc_id: int) -> UserModel | None:
        return await self.s.get(UserModel, acc_id)

    async def by_login(self, login: str) -> UserModel | None:
        return await self.s.scalar(select(UserModel).where(UserModel.login == login))

    async def by_email(self, email: str) -> UserModel | None:
        return await self.s.scalar(select(UserModel).where(UserModel.email == email))

    async def role_by_key(self, key: str) -> Role | None:
        """Найти системную роль по стабильному ключу (см. :class:`enums.BaseRole`)."""
        return await self.s.scalar(select(Role).where(Role.key == key))

    async def create(
        self,
        login: str,
        pass_hash: str | None,
        email: str | None = None,
        *,
        role_key: str = BaseRole.GUEST,
    ) -> UserModel:
        """Создать аккаунт с базовой ролью.

        :arg login: логин.
        :arg pass_hash: хеш пароля (``None`` для OAuth-only).
        :arg email: email (опционально).
        :arg role_key: ключ стартовой роли — по умолчанию ``guest`` (не
            верифицирован); ``user`` для уже верифицированных (напр. OAuth).
        :return: созданный аккаунт.
        """
        role = await self.role_by_key(role_key)
        acc = UserModel(
            login=login,
            pass_hash=pass_hash,
            email=email,
            role_id=role.id if role else None,
        )
        self.s.add(acc)
        await self.s.flush()
        acc.role = role
        return acc

    async def set_role_key(self, acc: UserModel, key: str) -> None:
        """Назначить аккаунту системную роль по ключу (если такая роль есть)."""
        role = await self.role_by_key(key)
        if role is not None:
            acc.role_id = role.id
            acc.role = role
            await self.s.flush()

    async def touch_login(self, acc: UserModel) -> None:
        """Обновить отметку последнего входа."""
        acc.last_login = utc_now()
        await self.s.flush()


__all__ = ["UserModel", "UserMngr"]
