"""Платёжный провайдер: секреты и привязка init/callback Lua-скриптов."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from orm.mixins import PkMixin, TsMixin


class PayProvider(PkMixin, TsMixin, Base):
    """Запись о платёжном провайдере (ЮKassa, Stripe, …).

    ``secrets_enc`` — зашифрованный (SecBox) JSON с секретами и уникальными
    данными платёжки (ключи API, shop_id, webhook-секрет и т.п.). В рантайме
    он расшифровывается и прокидывается в Lua-скрипты провайдера.

    Каждая платёжка работает по-своему, поэтому у провайдера два скрипта:
      * ``init_script_id`` — инициализация платежа (возвращает ссылку оплаты);
      * ``cb_script_id``   — обработка колбэка/возврата (проверка подписи).
    """

    __tablename__ = "pay_providers"

    slug: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Зашифрованный JSON секретов/доп-данных платёжки.
    secrets_enc: Mapped[str] = mapped_column(Text, default="", nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="RUB", nullable=False)

    init_script_id: Mapped[int | None] = mapped_column(
        ForeignKey("lua_scripts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cb_script_id: Mapped[int | None] = mapped_column(
        ForeignKey("lua_scripts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Несекретные дополнительные настройки провайдера.
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


__all__ = ["PayProvider"]
