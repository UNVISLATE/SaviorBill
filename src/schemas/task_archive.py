"""Pydantic-схемы для долговечного архива задач."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TaskArchiveListItem(BaseModel):
    id: int
    task_id: str
    kind: str
    operation: str
    status: str
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    initiator_type: str | None = None
    initiator_id: str | None = None
    error_message: str | None = None

    model_config = {"from_attributes": True}


class TaskArchiveDetail(BaseModel):
    id: int
    task_id: str
    kind: str
    operation: str
    status: str
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    initiator_type: str | None = None
    initiator_id: str | None = None
    error_message: str | None = None
    logs: list[Any] | None = Field(default_factory=list)
    meta: dict[str, Any] | None = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class TaskArchivePage(BaseModel):
    items: list[TaskArchiveListItem]
    total: int
    page: int
    page_size: int
