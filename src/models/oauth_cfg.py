"""OAuth/OIDC: конфигурация подключаемых провайдеров."""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from orm.mixins import PkMixin, TsMixin


class OAuthCfg(PkMixin, TsMixin, Base):
    """Доп. конфигурация: подключение внешнего OAuth/OIDC-провайдера.

    URL-эндпоинты можно не задавать, если указан ``issuer`` — тогда они
    подтягиваются через OIDC discovery (``/.well-known/openid-configuration``).
    ``client_secret`` хранится зашифрованным (см. utils.sec.box.SecBox).
    ``extra`` — место для особенностей конкретной платформы.
    """

    __tablename__ = "oauth_cfg"

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


__all__ = ["OAuthCfg"]
