"""Админ: запрещённые для регистрации email-домены (/api/v1/admin/settings/email-domains)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from dependencies.auth import get_banned_domains_mngr
from dependencies.rbac import require_perm
from models.banned_email_domains import BannedEmailDomainsMngr
from schemas.banned_email_domains import BannedEmailDomain, BannedEmailDomainCreate

router = APIRouter()


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


__all__ = ["router"]
