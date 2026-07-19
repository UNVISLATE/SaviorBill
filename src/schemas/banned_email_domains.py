"""Схемы для админки запрещённых для регистрации email-доменов."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from models.banned_email_domains import BannedEmailDomainModel


class BannedEmailDomain(BaseModel):
    domain: str
    reason: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, row: BannedEmailDomainModel) -> "BannedEmailDomain":
        return cls(domain=row.domain, reason=row.reason, created_at=row.created_at)


class BannedEmailDomainCreate(BaseModel):
    domain: str = Field(min_length=1, max_length=255)
    reason: str | None = Field(default=None, max_length=255)


__all__ = ["BannedEmailDomain", "BannedEmailDomainCreate"]
