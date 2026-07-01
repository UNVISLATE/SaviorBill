"""OAuth-провайдеры (OAuthProvidersModel) + менеджер (OAuthProvidersMngr)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, Boolean, DateTime, Integer, JSON, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from utils.datetime_utils import utc_now


class OAuthProvidersModel(Base):
    """подключение внешнего OAuth/OIDC-провайдера"""

    __tablename__ = "oauth_cfg"

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

    slug: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    client_secret_enc: Mapped[str] = mapped_column(Text, nullable=False)

    issuer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    authorize_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    token_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    userinfo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    jwks_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)

    scopes: Mapped[str] = mapped_column(
        String(255), default="openid email profile", nullable=False
    )
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class OAuthProvidersMngr:
    """CRUD для OAuth-провайдеров."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def by_id(self, provider_id: int) -> OAuthProvidersModel | None:
        return await self.s.get(OAuthProvidersModel, provider_id)

    async def by_slug(
        self, slug: str, *, enabled_only: bool = False
    ) -> OAuthProvidersModel | None:
        stmt = select(OAuthProvidersModel).where(OAuthProvidersModel.slug == slug)
        if enabled_only:
            stmt = stmt.where(OAuthProvidersModel.enabled.is_(True))
        return await self.s.scalar(stmt)

    async def list_all(self) -> list[OAuthProvidersModel]:
        rows = await self.s.scalars(
            select(OAuthProvidersModel).order_by(OAuthProvidersModel.id)
        )
        return list(rows)

    async def list_enabled(self) -> list[OAuthProvidersModel]:
        rows = await self.s.scalars(
            select(OAuthProvidersModel)
            .where(OAuthProvidersModel.enabled.is_(True))
            .order_by(OAuthProvidersModel.id)
        )
        return list(rows)

    async def create(self, **data) -> OAuthProvidersModel:
        provider = OAuthProvidersModel(**data)
        self.s.add(provider)
        await self.s.flush()
        return provider


__all__ = ["OAuthProvidersModel", "OAuthProvidersMngr"]
