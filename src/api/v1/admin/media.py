"""Админ: управление медиа (/api/v1/admin/media)."""

from __future__ import annotations

import hashlib
import mimetypes
import os
import re
import uuid

import valkey.asyncio as valkey
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from dependencies.media import get_media_mngr
from dependencies.rbac import require_perm
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.valkey import get_valkey_client
from models.system_media import SystemMediaMngr, SystemMediaModel
from models.user import UserModel
from schemas.media import Media
from schemas.page import Page
from services.account import drop_media
from services.audit import audit
from core.config import AppConfig
from messaging.mediabus import MediaBus
from utils.datetime_utils import utc_now
from utils.pagination import apply_sort, paginate, q_param, sort_param
from sqlalchemy import func, select

router = APIRouter()

_MEDIA_SORT_FIELDS = {"id", "created_at", "size", "status", "kind", "tag"}

# До 16 символов, только латиница и цифры (см. mediaworker/src/api/upload.py::_TAG_RE
# — то же правило по обе стороны, метка задаётся при загрузке и меняется здесь).
_TAG_RE = re.compile(r"^[A-Za-z0-9]{1,16}$")


class MediaTagIn(BaseModel):
    """Тело запроса на изменение метки медиа."""

    tag: str | None = Field(
        default=None,
        max_length=16,
        description="Новая метка (латиница+цифры, до 16 символов) или null — снять",
    )


def _bus(request: Request, vk: valkey.Valkey) -> MediaBus:
    cfg: AppConfig = request.app.state.settings
    return MediaBus(vk, cfg.MEDIA_TASK_STREAM, cfg.MEDIA_TASK_STREAM_MAXLEN, signing_key=cfg.BUS_SIGNING_KEY)


@router.get(
    "",
    response_model=Page[Media],
    dependencies=[Depends(require_perm("media.read"))],
    summary="Media",
    description="Все медиа (постранично), либо только владельца — фильтр "
    "`owner_id` для просмотра медиа конкретного пользователя из админского "
    "Drawer. `q` searches tag/mime (exact "
    f"substring); `sort` accepts {'/'.join(sorted(_MEDIA_SORT_FIELDS))}.",
)
async def list_media(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    owner_id: int | None = Query(default=None),
    q: str | None = Depends(q_param),
    sort: str | None = Depends(sort_param),
    mngr: SystemMediaMngr = Depends(get_media_mngr),
) -> Page[Media]:
    stmt = mngr.stmt_for_owner(owner_id) if owner_id is not None else select(SystemMediaModel)
    stmt = apply_sort(stmt, SystemMediaModel, sort, _MEDIA_SORT_FIELDS)
    if sort is None:
        stmt = stmt.order_by(SystemMediaModel.id.desc())
    if q:
        stmt = stmt.where(
            SystemMediaModel.tag.ilike(f"%{q}%")
            | SystemMediaModel.mime.ilike(f"%{q}%")
            | SystemMediaModel.token.ilike(f"%{q}%")
            | func.json_extract_path_text(SystemMediaModel.meta, "name").ilike(f"%{q}%")
        )
    items, total, has_more = await paginate(
        mngr.s, stmt, Media.from_model, limit=limit, offset=offset
    )
    return Page(items=items, total=total, limit=limit, offset=offset, has_more=has_more)


@router.delete(
    "/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete media",
)
async def delete_media(
    request: Request,
    media_id: int,
    mngr: SystemMediaMngr = Depends(get_media_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
    acc: UserModel = Depends(require_perm("media.delete")),
) -> None:
    media = await mngr.by_id(media_id)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    await drop_media(mngr, _bus(request, vk), media)
    await audit(
        mngr.s,
        action="media.delete",
        actor_id=acc.id,
        actor_role=acc.role.name if acc.role else None,
        target_type="media",
        target_id=str(media_id),
        ip=request.client.host if request.client else None,
        meta={"token": media.token, "backend": media.backend},
    )
    await mngr.s.commit()


@router.post(
    "/{media_id}/reconcile",
    dependencies=[Depends(require_perm("media.read"))],
    summary="Reconcile media artifacts",
    description="Queue a non-destructive physical artifact integrity check.",
)
async def reconcile_media(
    request: Request,
    media_id: int,
    mngr: SystemMediaMngr = Depends(get_media_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> dict:
    media = await mngr.by_id(media_id)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    await _bus(request, vk).enqueue_integrity_check(media.token)
    return {"token": media.token, "state": "queued"}


@router.get(
    "/{media_id}/reconcile",
    dependencies=[Depends(require_perm("media.read"))],
    summary="Get media reconciliation",
)
async def media_reconciliation(
    request: Request,
    media_id: int,
    mngr: SystemMediaMngr = Depends(get_media_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> dict:
    media = await mngr.by_id(media_id)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    result = await _bus(request, vk).integrity_status(media.token)
    return result or {"token": media.token, "state": "not_checked"}


@router.get(
    "/reconcile/batch",
    dependencies=[Depends(require_perm("media.read"))],
    summary="Queue a bounded media reconciliation batch",
)
async def reconcile_media_batch(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    after_id: int = Query(0, ge=0),
    mngr: SystemMediaMngr = Depends(get_media_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> dict:
    """Queue integrity checks without scanning Valkey or storage in billing."""
    rows = list(
        await mngr.s.scalars(
            select(SystemMediaModel)
            .where(SystemMediaModel.id > after_id)
            .order_by(SystemMediaModel.id)
            .limit(limit + 1)
        )
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    bus = _bus(request, vk)
    for media in rows:
        await bus.enqueue_integrity_check(media.token)
    next_after_id = rows[-1].id if rows else after_id
    return {
        "queued": len(rows),
        "after_id": after_id,
        "next_after_id": next_after_id,
        "has_more": has_more,
    }


@router.put(
    "/{media_id}/tag",
    response_model=Media,
    summary="Update media tag",
    description="Изменить UI-метку медиа (латиница+цифры, до 16 символов).",
)
async def update_media_tag(
    request: Request,
    media_id: int,
    body: MediaTagIn,
    mngr: SystemMediaMngr = Depends(get_media_mngr),
    acc: UserModel = Depends(require_perm("media.write")),
) -> Media:
    if body.tag is not None and not _TAG_RE.match(body.tag):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "tag must be 1-16 latin letters/digits",
        )
    media = await mngr.by_id(media_id)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    await mngr.set_tag(media, body.tag)
    await audit(
        mngr.s,
        action="media.tag",
        actor_id=acc.id,
        actor_role=acc.role.name if acc.role else None,
        target_type="media",
        target_id=str(media_id),
        ip=request.client.host if request.client else None,
        meta={"tag": body.tag},
    )
    await mngr.s.commit()
    return Media.from_model(media)


class MediaNameIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Название / имя файла")


@router.put(
    "/{media_id}/name",
    response_model=Media,
    summary="Update media name",
    description="Переименовать медиа-файл (сохраняется в meta.name).",
)
async def update_media_name(
    request: Request,
    media_id: int,
    body: MediaNameIn,
    mngr: SystemMediaMngr = Depends(get_media_mngr),
    acc: UserModel = Depends(require_perm("media.write")),
) -> Media:
    media = await mngr.by_id(media_id)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    new_meta = dict(media.meta or {})
    clean_name = body.name.strip()
    new_meta["name"] = clean_name
    media.meta = new_meta
    await audit(
        mngr.s,
        action="media.rename",
        actor_id=acc.id,
        actor_role=acc.role.name if acc.role else None,
        target_type="media",
        target_id=str(media_id),
        ip=request.client.host if request.client else None,
        meta={"name": clean_name, "token": media.token},
    )
    await mngr.s.commit()
    await mngr.s.refresh(media)
    return Media.from_model(media)


@router.get(
    "/reconcile/batch/status",
    dependencies=[Depends(require_perm("media.read"))],
    summary="Get bounded media reconciliation batch status",
    description="Reads the physical integrity check statuses for a bounded batch of media.",
)
async def get_reconcile_batch_status(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    after_id: int = Query(0, ge=0),
    mngr: SystemMediaMngr = Depends(get_media_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> dict:
    rows = list(
        await mngr.s.scalars(
            select(SystemMediaModel)
            .where(SystemMediaModel.id > after_id)
            .order_by(SystemMediaModel.id)
            .limit(limit)
        )
    )
    bus = _bus(request, vk)
    items = []
    summary = {
        "healthy": 0,
        "artifact_missing": 0,
        "artifact_corrupt": 0,
        "variant_missing": 0,
        "storage_unavailable": 0,
        "not_checked": 0,
    }
    for media in rows:
        st = await bus.integrity_status(media.token)
        state = (st or {}).get("state", "not_checked")
        if state in summary:
            summary[state] += 1
        else:
            summary["not_checked"] += 1
        items.append({"id": media.id, "token": media.token, "state": state, "details": st})
    return {
        "summary": summary,
        "total_in_batch": len(rows),
        "after_id": after_id,
        "items": items,
    }


@router.get(
    "/orphans",
    dependencies=[Depends(require_perm("media.read"))],
    summary="Preview orphaned media",
    description="Non-destructive preview report of unused media older than grace_sec.",
)
async def preview_orphaned_media(
    grace_sec: int = Query(3600, ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    mngr: SystemMediaMngr = Depends(get_media_mngr),
) -> dict:
    offset = (page - 1) * page_size
    orphans, total = await mngr.preview_orphans(grace_sec=grace_sec, limit=page_size, offset=offset)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "grace_sec": grace_sec,
        "items": [Media.from_model(m) for m in orphans],
    }

@router.post(
    "/cleanup",
    dependencies=[Depends(require_perm("media.cleanup"))],
    summary="Cleanup media",
    description="Delete unused media older than the grace period and queue file cleanup.",
)
async def cleanup_media(
    request: Request,
    mngr: SystemMediaMngr = Depends(get_media_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> dict:
    bus = _bus(request, vk)
    grace = await settings.get_int("media.cleanup_grace_sec", 3600)
    orphans = await mngr.orphans(grace_sec=grace or 0)
    for media in orphans:
        await drop_media(mngr, bus, media)
    await mngr.s.commit()
    return {"deleted": len(orphans)}


def _sniff_kind_mime(filepath: str) -> tuple[str, str]:
    try:
        with open(filepath, "rb") as f:
            header = f.read(512)
    except OSError:
        header = b""

    if header.startswith(b"\xff\xd8\xff"):
        return "image", "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", "image/png"
    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        return "image", "image/gif"
    if header.startswith(b"RIFF") and len(header) >= 12:
        fourcc = header[8:12]
        if fourcc == b"WEBP":
            return "image", "image/webp"
        if fourcc == b"AVI ":
            return "video", "video/x-msvideo"
    if b"<svg" in header.lower():
        return "svg", "image/svg+xml"
    if header.startswith(b"\x1aE\xdf\xa3"):
        return "video", "video/webm"
    if len(header) >= 8 and header[4:8] == b"ftyp":
        return "video", "video/mp4"

    guessed, _ = mimetypes.guess_type(filepath)
    if guessed:
        if guessed.startswith("video/"):
            return "video", guessed
        if guessed.startswith("image/"):
            return "image", guessed
        return "image", guessed

    return "image", "application/octet-stream"


@router.post(
    "/scan-orphans",
    dependencies=[Depends(require_perm("media.write"))],
    summary="Sync storage with database",
    description="Синхронизация хранилища: сканирует data/media на наличие не проиндексированных файлов (например, добавленных вручную или оставшихся после сброса БД), регистрирует их в системе, генерирует токены и кэш.",
)
async def scan_orphaned_files(
    request: Request,
    mngr: SystemMediaMngr = Depends(get_media_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
    acc: UserModel = Depends(require_perm("media.write")),
) -> dict:
    cfg: AppConfig = request.app.state.settings
    media_dir = cfg.media_dir
    if not media_dir.exists() or not media_dir.is_dir():
        return {"scanned": 0, "recovered_count": 0, "recovered": []}

    existing_rows = list(
        await mngr.s.execute(
            select(SystemMediaModel.token, SystemMediaModel.path, SystemMediaModel.variants)
        )
    )
    known_tokens = set()
    known_files = set()
    for token, path, variants in existing_rows:
        if token:
            known_tokens.add(token.lower())
        if path:
            known_files.add(os.path.basename(path).lower())
            known_files.add(str(path).replace("\\", "/").lower())
        if isinstance(variants, dict):
            if variants.get("media", {}).get("key"):
                known_files.add(os.path.basename(variants["media"]["key"]).lower())
            if variants.get("thumb", {}).get("key"):
                known_files.add(os.path.basename(variants["thumb"]["key"]).lower())
            for prev in variants.get("previews", []):
                if isinstance(prev, dict) and prev.get("key"):
                    known_files.add(os.path.basename(prev["key"]).lower())

    hex32_prefix_re = re.compile(r"^([a-f0-9]{32})\b", re.IGNORECASE)

    disk_files = []
    for root, _, files in os.walk(media_dir):
        for f in files:
            if f.endswith(".tmp") or f.startswith("."):
                continue
            full_p = os.path.join(root, f)
            rel_p = os.path.relpath(full_p, media_dir).replace("\\", "/")
            disk_files.append((f, rel_p, full_p))

    orphan_files = []
    for fname, rel_p, full_p in disk_files:
        fn_lower = fname.lower()
        rel_lower = rel_p.lower()
        m = hex32_prefix_re.match(fname)
        token_prefix = m.group(1).lower() if m else None

        if fn_lower in known_files or rel_lower in known_files:
            continue
        if token_prefix and token_prefix in known_tokens:
            continue
        orphan_files.append((fname, rel_p, full_p, token_prefix))

    groups: dict[str, list[tuple[str, str, str]]] = {}
    standalone: list[tuple[str, str, str]] = []

    for fname, rel_p, full_p, token_prefix in orphan_files:
        if token_prefix:
            groups.setdefault(token_prefix, []).append((fname, rel_p, full_p))
        else:
            standalone.append((fname, rel_p, full_p))

    recovered = []

    for tok, file_list in groups.items():
        main_tuple = next(
            (t for t in file_list if ".thumb." not in t[0] and ".preview." not in t[0]),
            file_list[0],
        )
        thumb_tuple = next((t for t in file_list if ".thumb." in t[0]), None)
        preview_tuples = [t for t in file_list if ".preview." in t[0]]

        main_fname, main_rel, main_full = main_tuple
        try:
            stat = os.stat(main_full)
            size = stat.st_size
        except OSError:
            continue

        kind, mime = _sniff_kind_mime(main_full)
        h = hashlib.sha256()
        with open(main_full, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        content_hash = h.hexdigest()

        variants = {
            "media": {
                "key": main_rel,
                "mime": mime,
                "size": size,
                "url": f"/api/media/{tok}",
            }
        }
        vk_file_mapping = {"main": main_rel}

        if thumb_tuple:
            _, t_rel, t_full = thumb_tuple
            try:
                t_stat = os.stat(t_full)
                variants["thumb"] = {
                    "key": t_rel,
                    "mime": "image/webp",
                    "size": t_stat.st_size,
                    "url": f"/api/media/{tok}.thumb",
                }
                vk_file_mapping["thumb"] = t_rel
            except OSError:
                pass

        if preview_tuples:
            variants["previews"] = []
            for p_fname, p_rel, p_full in preview_tuples:
                try:
                    p_stat = os.stat(p_full)
                    marker = ".preview."
                    suffix = (
                        p_fname.split(marker)[-1].rsplit(".", 1)[0]
                        if marker in p_fname
                        else "1"
                    )
                    variants["previews"].append({
                        "key": p_rel,
                        "mime": "image/webp",
                        "size": p_stat.st_size,
                        "url": f"/api/media/{tok}.preview.{suffix}",
                    })
                    vk_file_mapping[f"preview.{suffix}"] = p_rel
                except OSError:
                    pass

        row = SystemMediaModel(
            token=tok,
            kind=kind,
            path=main_rel,
            backend="fs",
            mime=mime,
            size=size,
            owner_id=None,
            tag="recovered",
            status="ready",
            content_hash=content_hash,
            variants=variants,
            meta={
                "name": main_fname,
                "recovered": True,
                "indexed_at": utc_now().isoformat(),
            },
        )
        mngr.s.add(row)
        await vk.hset(f"media:file:{tok}", mapping=vk_file_mapping)
        await vk.hset(f"media:status:{tok}", mapping={"state": "ready"})
        recovered.append({"token": tok, "filename": main_fname, "size": size, "kind": kind})

    for fname, rel_p, full_p in standalone:
        tok = uuid.uuid4().hex
        try:
            stat = os.stat(full_p)
            size = stat.st_size
        except OSError:
            continue

        kind, mime = _sniff_kind_mime(full_p)
        h = hashlib.sha256()
        with open(full_p, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        content_hash = h.hexdigest()

        variants = {
            "media": {
                "key": rel_p,
                "mime": mime,
                "size": size,
                "url": f"/api/media/{tok}",
            }
        }
        vk_file_mapping = {"main": rel_p}

        row = SystemMediaModel(
            token=tok,
            kind=kind,
            path=rel_p,
            backend="fs",
            mime=mime,
            size=size,
            owner_id=None,
            tag="recovered",
            status="ready",
            content_hash=content_hash,
            variants=variants,
            meta={"name": fname, "recovered": True, "indexed_at": utc_now().isoformat()},
        )
        mngr.s.add(row)
        await vk.hset(f"media:file:{tok}", mapping=vk_file_mapping)
        await vk.hset(f"media:status:{tok}", mapping={"state": "ready"})
        recovered.append({"token": tok, "filename": fname, "size": size, "kind": kind})

    if recovered:
        await audit(
            mngr.s,
            action="media.scan_orphans",
            actor_id=acc.id,
            actor_role=acc.role.name if acc.role else None,
            target_type="media",
            target_id="bulk",
            ip=request.client.host if request.client else None,
            meta={"recovered_count": len(recovered)},
        )
        await mngr.s.commit()

    return {
        "scanned": len(disk_files),
        "recovered_count": len(recovered),
        "recovered": recovered,
    }


__all__ = ["router"]
