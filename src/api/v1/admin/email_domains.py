"""Админ: запрещённые для регистрации email-домены (/api/v1/admin/settings/email-domains)."""

from __future__ import annotations

import csv
import io
import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.auth import get_banned_domains_mngr
from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from models.banned_email_domains import BannedEmailDomainModel, BannedEmailDomainsMngr
from models.user import UserModel
from schemas.banned_email_domains import (
    BannedEmailDomain,
    BannedEmailDomainBulkDeleteRequest,
    BannedEmailDomainCreate,
    BannedEmailDomainImportItem,
    BannedEmailDomainImportPreview,
    BannedEmailDomainsBulkRequest,
)
from services.audit import audit

router = APIRouter()
_DOMAIN_RE = re.compile(r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\Z")
_MAX_REMOTE_BYTES = 1_000_000


def _normalize_domain(value: str) -> str | None:
    domain = value.strip().lower().rstrip(".")
    return domain if _DOMAIN_RE.fullmatch(domain) else None


def _parse_domains(raw_text: str) -> list[tuple[int, str, str | None]]:
    rows: list[tuple[int, str, str | None]] = []
    for line_number, row in enumerate(csv.reader(io.StringIO(raw_text)), start=1):
        if not row or not any(cell.strip() for cell in row):
            continue
        value = row[0].strip()
        reason = row[1].strip() or None if len(row) > 1 else None
        rows.append((line_number, value, reason))
    return rows


async def _preview(
    raw_text: str, session: AsyncSession
) -> BannedEmailDomainImportPreview:
    parsed = _parse_domains(raw_text)
    existing = set(
        await session.scalars(select(BannedEmailDomainModel.domain))
    )
    seen: set[str] = set()
    items: list[BannedEmailDomainImportItem] = []
    counts = {"new": 0, "existing": 0, "duplicate": 0, "invalid": 0}
    for line, value, row_reason in parsed:
        domain = _normalize_domain(value)
        if domain is None:
            item = BannedEmailDomainImportItem(
                line=line, value=value, status="invalid", reason="invalid domain"
            )
        elif domain in seen:
            item = BannedEmailDomainImportItem(
                line=line, value=value, domain=domain, status="duplicate"
            )
        elif domain in existing:
            seen.add(domain)
            item = BannedEmailDomainImportItem(
                line=line, value=value, domain=domain, status="existing"
            )
        else:
            seen.add(domain)
            item = BannedEmailDomainImportItem(
                line=line, value=value, domain=domain, status="new", reason=row_reason
            )
        counts[item.status] += 1
        items.append(item)
    return BannedEmailDomainImportPreview(
        items=items,
        new_count=counts["new"],
        existing_count=counts["existing"],
        duplicate_count=counts["duplicate"],
        invalid_count=counts["invalid"],
    )


async def _load_bulk_text(body: BannedEmailDomainsBulkRequest) -> str:
    if body.raw_text.strip() and body.source_url:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "provide either raw_text or source_url, not both",
        )
    if body.raw_text.strip():
        return body.raw_text
    if not body.source_url:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "raw_text or source_url is required")

    parsed = urlparse(body.source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "source_url must be an http(s) URL")
    try:
        addresses = {
            ipaddress.ip_address(info[4][0])
            for info in socket.getaddrinfo(parsed.hostname, parsed.port, type=socket.SOCK_STREAM)
        }
    except (OSError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "source_url hostname cannot be resolved")
    if any(not address.is_global for address in addresses):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "source_url points to a private address")

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=5.0),
            follow_redirects=False,
            headers={"User-Agent": "SaviorBill admin domain importer"},
        ) as client:
            async with client.stream("GET", body.source_url) as response:
                response.raise_for_status()
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > _MAX_REMOTE_BYTES:
                    raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "source file is too large")
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > _MAX_REMOTE_BYTES:
                        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "source file is too large")
                    chunks.append(chunk)
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"source file could not be fetched: {exc}") from exc
    return b"".join(chunks).decode("utf-8-sig", errors="replace")


@router.get(
    "",
    response_model=list[BannedEmailDomain],
    dependencies=[Depends(require_perm("settings.email_domains.read"))],
    summary="List banned email domains",
)
async def list_banned_domains(
    mngr: BannedEmailDomainsMngr = Depends(get_banned_domains_mngr),
) -> list[BannedEmailDomain]:
    rows = await mngr.list_all()
    return [BannedEmailDomain.from_model(r) for r in rows]


@router.post(
    "",
    response_model=BannedEmailDomain,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("settings.email_domains.edit"))],
    summary="Ban an email domain",
    description="Registration attempts with an email on this domain will be rejected.",
)
async def add_banned_domain(
    body: BannedEmailDomainCreate,
    mngr: BannedEmailDomainsMngr = Depends(get_banned_domains_mngr),
) -> BannedEmailDomain:
    row = await mngr.add(body.domain, body.reason)
    await mngr.s.commit()
    return BannedEmailDomain.from_model(row)


@router.post(
    "/bulk/preview",
    response_model=BannedEmailDomainImportPreview,
    dependencies=[Depends(require_perm("settings.email_domains.edit"))],
    summary="Preview bulk email-domain import",
)
async def preview_banned_domains(
    body: BannedEmailDomainsBulkRequest,
    session: AsyncSession = Depends(get_db_session),
) -> BannedEmailDomainImportPreview:
    return await _preview(await _load_bulk_text(body), session)


@router.post(
    "/bulk",
    response_model=BannedEmailDomainImportPreview,
    status_code=status.HTTP_201_CREATED,
    summary="Import email domains in bulk",
)
async def import_banned_domains(
    body: BannedEmailDomainsBulkRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    mngr: BannedEmailDomainsMngr = Depends(get_banned_domains_mngr),
    acc: UserModel = Depends(require_perm("settings.email_domains.edit")),
) -> BannedEmailDomainImportPreview:
    preview = await _preview(await _load_bulk_text(body), session)
    for item in preview.items:
        if item.status != "new" or item.domain is None:
            continue
        await mngr.add(item.domain, item.reason or body.reason)
    await audit(
        session,
        action="email_domain.bulk_import",
        actor_id=acc.id,
        actor_role=acc.role.name if acc.role else None,
        target_type="email_domain",
        target_id=None,
        ip=request.client.host if request.client else None,
        meta={
            "new": preview.new_count,
            "existing": preview.existing_count,
            "duplicate": preview.duplicate_count,
            "invalid": preview.invalid_count,
        },
    )
    await session.commit()
    return preview


@router.delete(
    "/{domain}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("settings.email_domains.edit"))],
    summary="Unban an email domain",
)
async def remove_banned_domain(
    domain: str,
    mngr: BannedEmailDomainsMngr = Depends(get_banned_domains_mngr),
) -> None:
    ok = await mngr.remove(domain)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "domain not found")
    await mngr.s.commit()


@router.post(
    "/bulk/delete",
    response_model=dict[str, int],
    summary="Remove email domains in bulk",
)
async def remove_banned_domains(
    body: BannedEmailDomainBulkDeleteRequest,
    request: Request,
    mngr: BannedEmailDomainsMngr = Depends(get_banned_domains_mngr),
    acc: UserModel = Depends(require_perm("settings.email_domains.edit")),
) -> dict[str, int]:
    normalized = {_normalize_domain(value) for value in body.domains}
    domains = {value for value in normalized if value is not None}
    removed = 0
    for domain in domains:
        if await mngr.remove(domain):
            removed += 1
    await audit(
        mngr.s,
        action="email_domain.bulk_delete",
        actor_id=acc.id,
        actor_role=acc.role.name if acc.role else None,
        target_type="email_domain",
        target_id=None,
        ip=request.client.host if request.client else None,
        meta={"requested": len(body.domains), "removed": removed},
    )
    await mngr.s.commit()
    return {"requested": len(body.domains), "removed": removed}


__all__ = ["router"]
