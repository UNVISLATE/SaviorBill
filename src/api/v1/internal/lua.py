"""Внутренний API выдачи артефактов Lua-скриптов (.lua / .tar.gz с .so) для LuaWorker."""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.internal.service_keys import require_lua_token
from core.config import AppConfig
from dependencies.db import get_db_session
from models.system_scripts import LuaScriptVersionModel, SystemScriptsModel

router = APIRouter(prefix="/lua")


@router.get(
    "/artifacts/{script_id}/{version}",
    dependencies=[Depends(require_lua_token)],
    summary="Pull Lua script or native bundle artifact",
)
async def get_lua_artifact(
    script_id: int,
    version: int,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    cfg: AppConfig = request.app.state.settings
    ver = await session.scalar(
        select(LuaScriptVersionModel).where(
            LuaScriptVersionModel.script_id == script_id,
            LuaScriptVersionModel.version == version,
        )
    )
    if ver is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "script version not found")

    headers: dict[str, str] = {
        "X-Has-Native": "1" if ver.has_native else "0",
    }

    if ver.artifact_backend == "s3" and ver.artifact_key and cfg.S3_BUCKET:
        import aioboto3

        s3_sess = aioboto3.Session()
        async with s3_sess.client(
            "s3",
            endpoint_url=cfg.S3_ENDPOINT,
            region_name=cfg.S3_REGION,
            aws_access_key_id=cfg.S3_KEY,
            aws_secret_access_key=cfg.s3_secret,
        ) as client:
            resp = await client.get_object(Bucket=cfg.S3_BUCKET, Key=ver.artifact_key)
            data = await resp["Body"].read()
        sha = ver.sha256 or hashlib.sha256(data).hexdigest()
        headers["X-Artifact-SHA256"] = sha
        is_bundle = ver.artifact_key.endswith(".tar.gz") or ver.has_native
        headers["X-Artifact-Type"] = "tar.gz" if is_bundle else "lua"
        return Response(
            content=data,
            media_type="application/gzip" if is_bundle else "text/x-lua",
            headers=headers,
        )

    if ver.artifact_blob is not None:
        sha = ver.sha256 or hashlib.sha256(ver.artifact_blob).hexdigest()
        headers["X-Artifact-SHA256"] = sha
        headers["X-Artifact-Type"] = "tar.gz"
        return Response(content=ver.artifact_blob, media_type="application/gzip", headers=headers)

    if ver.code is not None:
        raw = ver.code.encode("utf-8")
        headers["X-Artifact-SHA256"] = ver.sha256 or hashlib.sha256(raw).hexdigest()
        headers["X-Artifact-Type"] = "lua"
        return Response(content=raw, media_type="text/x-lua", headers=headers)

    # Fallback на локальную ФС (для старых версий до миграции 0003).
    base = Path(cfg.LUA_SCRIPTS_DIR).resolve()
    target = (base / ver.filename).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid script path")
    if not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "script artifact file missing")
    raw = target.read_bytes()
    headers["X-Artifact-SHA256"] = ver.sha256 or hashlib.sha256(raw).hexdigest()
    headers["X-Artifact-Type"] = "lua"
    return Response(content=raw, media_type="text/x-lua", headers=headers)


__all__ = ["router"]
