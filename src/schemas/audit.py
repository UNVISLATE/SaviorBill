"""Схема записи аудит-журнала (админ-ответ)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AuditEntry(BaseModel):
    """Запись аудит-журнала."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ts: datetime
    actor_account_id: int | None = None
    actor_role: str | None = None
    action: str
    target_type: str | None = None
    target_id: str | None = None
    ip: str | None = None
    meta: dict = Field(default_factory=dict)
    result: str

    @classmethod
    def from_model(cls, m) -> "AuditEntry":  # noqa: ANN001 — AuditLogModel
        """Преобразование ORM-записи аудита в схему ответа."""
        return cls(
            id=m.id,
            ts=m.ts,
            actor_account_id=m.actor_account_id,
            actor_role=m.actor_role,
            action=m.action,
            target_type=m.target_type,
            target_id=m.target_id,
            ip=m.ip,
            meta=m.meta or {},
            result=m.result,
        )


__all__ = ["AuditEntry"]
