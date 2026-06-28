"""OAuth/OIDC: привязка внешней учётки к локальному аккаунту."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base
from orm.mixins import PkMixin, TsMixin

if TYPE_CHECKING:
    from models.user import Account


class OAuthConn(PkMixin, TsMixin, Base):
    """Привязка внешней OAuth-учётки к локальному аккаунту."""

    __tablename__ = "oauth_conns"
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_oauth_provider_subject"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # slug провайдера из OAuthCfg.
    provider: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # Идентификатор пользователя у провайдера (OIDC claim ``sub``).
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    account: Mapped["Account"] = relationship(back_populates="oauth_conns")


__all__ = ["OAuthConn"]
