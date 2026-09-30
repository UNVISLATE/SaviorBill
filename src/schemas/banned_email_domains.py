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


class BannedEmailDomainsBulkRequest(BaseModel):
    """Raw newline/CSV payload for a bulk domain operation."""

    raw_text: str = Field(default="", max_length=3_000_000)
    source_url: str | None = Field(default=None, max_length=2048)
    reason: str | None = Field(default=None, max_length=255)


class BannedEmailDomainImportItem(BaseModel):
    line: int
    value: str
    domain: str | None = None
    status: str
    reason: str | None = None


class BannedEmailDomainImportPreview(BaseModel):
    items: list[BannedEmailDomainImportItem]
    new_count: int
    existing_count: int
    duplicate_count: int
    invalid_count: int


class BannedEmailDomainBulkDeleteRequest(BaseModel):
    domains: list[str] = Field(min_length=1, max_length=10_000)


__all__ = [
    "BannedEmailDomain",
    "BannedEmailDomainCreate",
    "BannedEmailDomainsBulkRequest",
    "BannedEmailDomainImportItem",
    "BannedEmailDomainImportPreview",
    "BannedEmailDomainBulkDeleteRequest",
]
