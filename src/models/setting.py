"""Key-value настройки системы (SMTP, флаги и т.п.)."""

from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from orm.mixins import TsMixin


class Setting(TsMixin, Base):
    """Настройка системы вида ключ-значение.

    Значение хранится строкой (для структур — JSON-строкой). ``is_secret``
    помечает значения, которые нужно шифровать через SecBox (пароли SMTP и
    т.п.). Часть значений кэшируется в Valkey (см. SettingsMngr).
    """

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


__all__ = ["Setting"]
