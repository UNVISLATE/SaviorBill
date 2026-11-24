from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api.v1.internal.lua import get_lua_artifact
from core.config import AppConfig
from models.email_templates import EmailMngr
from security.sec.secrets.resolve import _norm_pem

pytestmark = pytest.mark.unit


def test_email_sync_to_fs_defaults_by_storage_backend() -> None:
    cfg_fs = AppConfig(
        SECRET_KEY="x" * 32,
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        STORAGE_BACKEND="fs",
    )
    assert cfg_fs.email_sync_to_fs is True

    cfg_s3 = AppConfig(
        SECRET_KEY="x" * 32,
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        STORAGE_BACKEND="s3",
    )
    assert cfg_s3.email_sync_to_fs is False

    cfg_override = AppConfig(
        SECRET_KEY="x" * 32,
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        STORAGE_BACKEND="s3",
        EMAIL_SYNC_TO_FS=True,
    )
    assert cfg_override.email_sync_to_fs is True


@pytest.mark.asyncio
async def test_email_mngr_skips_fs_when_sync_disabled(tmp_path) -> None:
    session = MagicMock()
    session.scalar = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.flush = AsyncMock()

    mngr = EmailMngr(session, str(tmp_path), sync_to_fs=False)
    data = SimpleNamespace(
        slug="welcome",
        name="Welcome",
        subject="Hi",
        body="<p>Hello</p>",
        is_html=True,
        description=None,
    )
    row = await mngr.create(data)
    assert row.body == "<p>Hello</p>"
    assert list(tmp_path.iterdir()) == []


def test_norm_pem_unescapes_single_line_env() -> None:
    raw = "-----BEGIN PUBLIC KEY-----\\nABC\\n-----END PUBLIC KEY-----"
    assert _norm_pem(raw) == "-----BEGIN PUBLIC KEY-----\nABC\n-----END PUBLIC KEY-----"


@pytest.mark.asyncio
async def test_get_lua_artifact_serves_db_code_with_sha_header() -> None:
    ver = SimpleNamespace(
        script_id=1,
        version=2,
        filename="services/demo/v2.lua",
        sha256="deadbeef",
        code="return { handle = function() return {} end }",
        artifact_backend="db",
        artifact_key=None,
        artifact_blob=None,
        has_native=False,
    )
    session = MagicMock()
    session.scalar = AsyncMock(return_value=ver)
    req = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=SimpleNamespace(S3_BUCKET=None, LUA_SCRIPTS_DIR="/nonexistent")
            )
        )
    )

    resp = await get_lua_artifact(1, 2, req, session=session)
    assert resp.status_code == 200
    assert resp.headers["X-Artifact-Type"] == "lua"
    assert resp.headers["X-Artifact-SHA256"] == "deadbeef"
    assert resp.headers["X-Has-Native"] == "0"
    assert b"return { handle" in resp.body
