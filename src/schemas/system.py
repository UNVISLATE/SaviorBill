from __future__ import annotations

from pydantic import BaseModel, Field


class HealthCheck(BaseModel):
    """Service health check."""

    status: str = Field(default="ok", description="Service status")
    app_name: str = Field(default="SaviorBill", description="App name")
    app_version: str = Field(default="0.0.1dev", description="App version")


__all__ = ["HealthCheck"]
