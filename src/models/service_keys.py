"""Пул цифровых ключей услуги (ServiceKeysModel) + менеджер (ServiceKeysMngr)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, Boolean, DateTime, ForeignKey, Integer, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from utils.datetime_utils import utc_now
from utils.sec.box import SecBox


class ServiceKeysModel(Base):
    """Цифровые ключи для выдачи, если услуга - цифровой ключ"""

    __tablename__ = "digi_keys"

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

    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Хранится зашифрованным через SecBox (Fernet) — см. ServiceKeysMngr.
    # Text, а не String(N): шифротекст длиннее исходного значения.
    value: Mapped[str] = mapped_column(Text, nullable=False)
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ServiceKeysMngr:
    """CRUD для цифровых ключей услуг. Значения ключей хранятся зашифрованными
    (``SecBox``/Fernet) и расшифровываются только при выдаче пользователю или
    явном раскрытии обладателем права ``ownersec.servicekeys.read``.
    """

    def __init__(self, session: AsyncSession, box: SecBox) -> None:
        self.s = session
        self.box = box

    async def by_id(self, key_id: int) -> ServiceKeysModel | None:
        return await self.s.get(ServiceKeysModel, key_id)

    async def list_for_service(self, service_id: int) -> list[ServiceKeysModel]:
        rows = await self.s.scalars(
            select(ServiceKeysModel)
            .where(ServiceKeysModel.service_id == service_id)
            .order_by(ServiceKeysModel.id)
        )
        return list(rows)

    async def list_available(self, service_id: int) -> list[ServiceKeysModel]:
        rows = await self.s.scalars(
            select(ServiceKeysModel)
            .where(
                ServiceKeysModel.service_id == service_id,
                ServiceKeysModel.is_used.is_(False),
            )
            .order_by(ServiceKeysModel.id)
        )
        return list(rows)

    async def count_available(self, service_id: int) -> int:
        """Сколько неиспользованных ключей осталось у услуги (для ``out_of_stock``)."""
        n = await self.s.scalar(
            select(func.count())
            .select_from(ServiceKeysModel)
            .where(
                ServiceKeysModel.service_id == service_id,
                ServiceKeysModel.is_used.is_(False),
            )
        )
        return int(n or 0)

    async def create(self, service_id: int, value: str) -> ServiceKeysModel:
        """Создать один ключ (значение шифруется перед сохранением)."""
        key = ServiceKeysModel(service_id=service_id, value=self.box.seal(value))
        self.s.add(key)
        await self.s.flush()
        return key

    async def create_batch(
        self, service_id: int, values: list[str]
    ) -> tuple[list[ServiceKeysModel], int]:
        """Массово добавить ключи (готовый список — без парсинга свободного текста).

        Дедупликация — только в пределах присланного списка (сравнение открытых
        значений против уже сохранённых в БД потребовало бы расшифровки всего
        пула и не выполняется).

        :arg service_id: услуга, к которой относится пул.
        :arg values: список открытых значений ключей.
        :return: (созданные ключи, число пропущенных дублей внутри запроса).
        """
        seen: set[str] = set()
        created: list[ServiceKeysModel] = []
        skipped = 0
        for value in values:
            value = value.strip()
            if not value or value in seen:
                skipped += 1
                continue
            seen.add(value)
            key = ServiceKeysModel(service_id=service_id, value=self.box.seal(value))
            self.s.add(key)
            created.append(key)
        await self.s.flush()
        return created, skipped

    def reveal(self, key: ServiceKeysModel) -> str:
        """Расшифровать значение ключа (только для ``ownersec.servicekeys.read``)."""
        return self.box.open(key.value)

    async def delete(self, key_id: int) -> None:
        key = await self.by_id(key_id)
        if key is not None:
            await self.s.delete(key)
            await self.s.flush()


__all__ = ["ServiceKeysModel", "ServiceKeysMngr"]

