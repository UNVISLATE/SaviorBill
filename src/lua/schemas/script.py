"""Схемы Lua-скриптов для админ-CRUD (Request/Response).

Отличаются от схем контекста (user/service/payment/…): здесь — регистрация,
замена и выдача метаданных зарегистрированных скриптов.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LuaScript(BaseModel):
    """Registered Lua script."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str | None = None
    kind: str
    filename: str
    actions: list = Field(
        default_factory=list,
        description="Supported script actions",
    )
    settings: dict = Field(
        default_factory=dict,
        description="Shared script settings",
    )
    is_active: bool
    current_version: int = 1
    lock_version: int = Field(
        default=0,
        description="Optimistic concurrency counter (send back unchanged on save)",
    )

    @classmethod
    def from_model(cls, m) -> "LuaScript":  # noqa: ANN001 — SystemScriptsModel
        """Явное преобразование ORM-скрипта в схему ответа."""
        return cls.model_validate(m)


class LuaScriptDetail(LuaScript):
    """Lua script with body."""

    code: str = Field(description="Lua script body")
    version: int = Field(description="Version of the returned code")

    @classmethod
    def from_model_with_code(
        cls, m, code: str, version: int | None = None
    ) -> "LuaScriptDetail":  # noqa: ANN001
        """Явное преобразование ORM-скрипта + прочитанного тела в схему ответа."""
        return cls(
            id=m.id,
            slug=m.slug,
            name=m.name,
            kind=m.kind,
            filename=m.filename,
            actions=m.actions,
            settings=m.settings,
            is_active=m.is_active,
            current_version=m.current_version,
            lock_version=m.lock_version,
            code=code,
            version=version if version is not None else m.current_version,
        )


class LuaScriptVersion(BaseModel):
    """Lua script version metadata (no code body — see LuaScriptVersionDetail)."""

    model_config = ConfigDict(from_attributes=True)

    version: int
    sha256: str | None = None
    commit_message: str | None = None
    created_at: str
    created_by: int | None = None

    @classmethod
    def from_model(cls, m) -> "LuaScriptVersion":  # noqa: ANN001
        return cls(
            version=m.version,
            sha256=m.sha256,
            commit_message=m.commit_message,
            created_at=m.created_at.isoformat(),
            created_by=m.created_by,
        )


class LuaScriptVersionDetail(LuaScriptVersion):
    """Lua script version with code body."""

    code: str = Field(description="Lua script body at this version")


class LuaScriptUpload(BaseModel):
    """Create Lua script."""

    slug: str = Field(min_length=2, max_length=64, description="Unique script slug")
    name: str | None = Field(
        default=None, max_length=128, description="Display name (optional)"
    )
    kind: str = Field(default="service", description="service | payment | generic")
    actions: list[str] = Field(
        default_factory=list,
        description="Supported script actions",
    )
    code: str = Field(
        min_length=1,
        max_length=100_000,
        description="Lua script body",
    )
    settings: dict = Field(
        default_factory=dict,
        description="Shared script settings (optional)",
    )
    description: str | None = Field(
        default=None, max_length=2048, description="Description (optional)"
    )
    commit_message: str | None = Field(
        default=None,
        max_length=512,
        description="Commit message for the initial version (optional)",
    )


class LuaScriptPatch(BaseModel):
    """Update Lua script."""

    code: str | None = Field(
        default=None,
        min_length=1,
        max_length=100_000,
        description="New Lua script body (optional)",
    )
    settings: dict | None = Field(
        default=None,
        description="New script settings; replaces all",
    )
    commit_message: str | None = Field(
        default=None,
        max_length=512,
        description="Commit message for the new version (only used if code changed)",
    )
    lock_version: int | None = Field(
        default=None,
        description=(
            "Expected lock_version (optimistic concurrency) — 409 if it no "
            "longer matches the stored value"
        ),
    )


class LuaScriptActivate(BaseModel):
    """Activate an existing historical version (rollback without a new file)."""

    lock_version: int | None = Field(
        default=None, description="Expected lock_version (optimistic concurrency)"
    )


class LuaScriptLint(BaseModel):
    """Compile-check arbitrary Lua code (no DB/file side effects)."""

    code: str = Field(min_length=1, max_length=100_000, description="Lua code to lint")


class LuaScriptLintResult(BaseModel):
    """Lint result."""

    ok: bool
    error: str | None = None


class LuaScriptTestRun(BaseModel):
    """Sandboxed test-run of a script (draft or saved) with a fake ctx."""

    code: str | None = Field(
        default=None,
        max_length=100_000,
        description="Code to test-run (defaults to the script's saved current version)",
    )
    ctx: dict = Field(default_factory=dict, description="Fake ctx passed to handle(ctx)")


class LuaScriptTestRunResult(BaseModel):
    """Sandboxed test-run result."""

    public: dict = Field(default_factory=dict)
    private: dict = Field(default_factory=dict)
    logs: list = Field(default_factory=list)
    error: str | None = None


__all__ = [
    "LuaScript",
    "LuaScriptDetail",
    "LuaScriptVersion",
    "LuaScriptVersionDetail",
    "LuaScriptUpload",
    "LuaScriptPatch",
    "LuaScriptActivate",
    "LuaScriptLint",
    "LuaScriptLintResult",
    "LuaScriptTestRun",
    "LuaScriptTestRunResult",
]
