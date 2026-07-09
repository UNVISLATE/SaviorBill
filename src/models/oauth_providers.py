"""OAuth-провайдеры (OAuthProvidersModel) + менеджер (OAuthProvidersMngr)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    func,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base
from utils.datetime_utils import utc_now


class OAuthProvidersModel(Base):
    """подключение внешнего OAuth-провайдера (флоу через Lua-скрипт)"""

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

    # Единый action-driven Lua-скрипт провайдера (start/callback). Обязателен для
    # исполнения OAuth-флоу — как у платёжных провайдеров.
    script_id: Mapped[int | None] = mapped_column(
        ForeignKey("lua_scripts.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    # Зашифрованный JSON секретов/доп-данных провайдера (client_id/secret и пр.),
    # прокидывается в скрипт как ctx.secrets.*. Единственный источник кредов —
    # легаси-поля (client_id/authorize_url/…) удалены, весь Lua-флоу action-driven
    # и получает полные данные запроса/секреты через ctx, а не через отдельные
    # именованные колонки конфигурации.
    secrets_enc: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Иконка провайдера для UI (ровно одно вложение — прямой FK, отдельная
    # таблица вложений тут избыточна, в отличие от товаров с несколькими медиа).
    icon_media_id: Mapped[int | None] = mapped_column(
        ForeignKey("system_media.id", ondelete="SET NULL"), nullable=True
    )

    scopes: Mapped[str] = mapped_column(
        String(255), default="openid email profile", nullable=False
    )
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    icon: Mapped["SystemMediaModel | None"] = relationship(  # noqa: F821
        "SystemMediaModel", lazy="joined"
    )


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
