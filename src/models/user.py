"""Учётная запись пользователя (UserModel) + менеджер (UserMngr)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from secrets import token_urlsafe
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
    from models.system_media import SystemMediaModel


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

    # Аватар пользователя — ссылка на медиа (см. SystemMediaModel). NULL — нет.
    avatar_media_id: Mapped[int | None] = mapped_column(
        ForeignKey("system_media.id", ondelete="SET NULL"), nullable=True
    )

    # Собственный реферальный код (для приглашения других пользователей).
    ref_code: Mapped[str | None] = mapped_column(
        String(16), unique=True, index=True, nullable=True
    )
    # Пригласивший пользователь (реферер). NULL — регистрация без реферала.
    referred_by: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    role: Mapped["Role | None"] = relationship(back_populates="accounts", lazy="joined")
    oauth_conns: Mapped[list["UserOauthModel"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )
    # Аватар — иконка профиля (см. схему media.py::_media_url для готового URL).
    avatar_media: Mapped["SystemMediaModel | None"] = relationship(
        "SystemMediaModel", foreign_keys=[avatar_media_id], lazy="joined"
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

    async def by_login_or_email(self, identifier: str) -> UserModel | None:
        """Найти аккаунт по логину, а если не нашли — по email (для входа).

        Позволяет пользователю логиниться и логином, и email в одном и том же
        поле формы — без эвристики "похоже на email" на стороне клиента.
        Проверка последовательная (не единым OR-запросом), т.к. `login` одного
        аккаунта теоретически может совпасть с `email` другого — OR-запрос дал
        бы недетерминированный результат при коллизии; последовательный
        поиск с приоритетом `login` устраняет двусмысленность.
        """
        return await self.by_login(identifier) or await self.by_email(identifier)

    async def by_ref_code(self, code: str) -> UserModel | None:
        """Найти аккаунт по его реферальному коду."""
        return await self.s.scalar(select(UserModel).where(UserModel.ref_code == code))

    async def _gen_ref_code(self) -> str:
        """Сгенерировать уникальный реферальный код."""
        for _ in range(8):
            code = token_urlsafe(6)[:12]
            if await self.by_ref_code(code) is None:
                return code
        return token_urlsafe(9)[:16]

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
        ref_by: str | None = None,
    ) -> UserModel:
        """Создать аккаунт с базовой ролью.

        :arg login: логин.
        :arg pass_hash: хеш пароля (``None`` для OAuth-only).
        :arg email: email (опционально).
        :arg role_key: ключ стартовой роли — по умолчанию ``guest`` (не
            верифицирован); ``user`` для уже верифицированных (напр. OAuth).
        :arg ref_by: реферальный код пригласившего (опционально); если найден —
            заполняется ``referred_by``.
        :return: созданный аккаунт.
        """
        role = await self.role_by_key(role_key)
        referrer = await self.by_ref_code(ref_by) if ref_by else None
        acc = UserModel(
            login=login,
            pass_hash=pass_hash,
            email=email,
            role_id=role.id if role else None,
            ref_code=await self._gen_ref_code(),
            referred_by=referrer.id if referrer else None,
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
