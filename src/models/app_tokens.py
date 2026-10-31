"""Модель и менеджер постоянных API-токенов приложений (App Tokens)."""

from __future__ import annotations

from datetime import datetime
import hashlib
import ipaddress
import secrets
import string
from typing import Sequence

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base
from utils.datetime_utils import utc_now


def generate_app_token() -> tuple[str, str, str]:
    """Генерирует новый App Token с криптостойкой энтропией.

    Формат: sbapp_live_{tag}_{secret}, где tag — 4 случайных символа в нижнем регистре.
    Возвращает:
      - secret_token: полный токен (например, "sbapp_live_a1b2_...")
      - token_prefix: безопасный префикс для UI и идентификации ("sbapp_live_a1b2_")
      - token_hash: SHA-256 хэш полного токена для безопасного хранения в БД.
    """
    tag = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(4))
    prefix = f"sbapp_live_{tag}_"
    raw_secret = secrets.token_urlsafe(32)
    full_token = f"{prefix}{raw_secret}"
    token_hash = hash_app_token(full_token)
    return full_token, prefix, token_hash


def hash_app_token(full_token: str) -> str:
    """Вычисляет SHA-256 хэш от токена приложения."""
    return hashlib.sha256(full_token.strip().encode("utf-8")).hexdigest()


class AppTokenModel(Base):
    """Постоянный токен приложения (App Token) со Scoped RBAC."""

    __tablename__ = "app_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_prefix: Mapped[str] = mapped_column(String(24), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]", nullable=False)
    ip_allowlist: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_by_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )

    creator = relationship("UserModel", foreign_keys=[created_by_account_id], lazy="selectin")

    @property
    def created_by_login(self) -> str | None:
        return self.creator.login if self.creator else None

    @property
    def perms_tree(self) -> dict:
        """Древовидная структура прав для быстрой проверки через has_perm()."""
        tree: dict = {}
        for p in self.permissions:
            node = tree
            parts = p.split(".")
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = True
        return tree

    def check_ip_allowed(self, client_ip: str) -> bool:
        """Проверить, разрешен ли IP-адрес клиента по белому списку токена."""
        if not self.ip_allowlist:
            return True
        try:
            client_addr = ipaddress.ip_address(client_ip)
        except ValueError:
            return False

        for rule in self.ip_allowlist:
            rule = rule.strip()
            if not rule:
                continue
            try:
                if "/" in rule:
                    if client_addr in ipaddress.ip_network(rule, strict=False):
                        return True
                else:
                    if client_addr == ipaddress.ip_address(rule):
                        return True
            except ValueError:
                continue
        return False


class AppTokensMngr:
    """Менеджер управления токенами приложений."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def list_tokens(self, account_id: int | None = None) -> Sequence[AppTokenModel]:
        stmt = select(AppTokenModel).order_by(AppTokenModel.created_at.desc())
        if account_id is not None:
            stmt = stmt.where(AppTokenModel.created_by_account_id == account_id)
        res = await self.s.scalars(stmt)
        return res.all()

    async def by_id(self, token_id: int) -> AppTokenModel | None:
        stmt = select(AppTokenModel).where(AppTokenModel.id == token_id)
        return await self.s.scalar(stmt)

    async def by_hash(self, token_hash: str) -> AppTokenModel | None:
        stmt = select(AppTokenModel).where(AppTokenModel.token_hash == token_hash)
        return await self.s.scalar(stmt)

    async def create(
        self,
        name: str,
        description: str | None,
        permissions: list[str],
        ip_allowlist: list[str] | None,
        created_by_account_id: int | None,
        expires_at: datetime | None,
    ) -> tuple[AppTokenModel, str]:
        secret_token, prefix, token_hash = generate_app_token()
        token = AppTokenModel(
            name=name,
            description=description,
            token_prefix=prefix,
            token_hash=token_hash,
            permissions=permissions,
            ip_allowlist=ip_allowlist,
            created_by_account_id=created_by_account_id,
            expires_at=expires_at,
        )
        self.s.add(token)
        await self.s.flush()
        return token, secret_token

    async def revoke(self, token_id: int, revoked_by_account_id: int | None) -> AppTokenModel | None:
        token = await self.by_id(token_id)
        if not token:
            return None
        token.is_revoked = True
        token.revoked_at = utc_now()
        token.revoked_by_account_id = revoked_by_account_id
        await self.s.flush()
        return token

    async def delete(self, token_id: int) -> bool:
        token = await self.by_id(token_id)
        if not token:
            return False
        await self.s.delete(token)
        await self.s.flush()
        return True

    async def touch(self, token_id: int, ip: str | None) -> None:
        token = await self.by_id(token_id)
        if token:
            token.last_used_at = utc_now()
            if ip:
                token.last_used_ip = ip
            await self.s.flush()


__all__ = ["AppTokenModel", "AppTokensMngr", "generate_app_token", "hash_app_token"]
