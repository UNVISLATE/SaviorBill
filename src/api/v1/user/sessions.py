"""Current user's refresh-session inventory and revocation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from dependencies.auth import get_current_acc, get_token_svc
from dependencies.rbac import require_perm
from models.user import UserModel
from schemas.user import SessionOut
from services.audit import audit
from services.auth import TokenSvc

router = APIRouter()


@router.get(
    "/me/sessions",
    response_model=list[SessionOut],
    dependencies=[Depends(require_perm("user.profile.read"))],
    summary="Current user's active sessions",
)
async def my_sessions(
    request: Request,
    acc: UserModel = Depends(get_current_acc),
    tokens: TokenSvc = Depends(get_token_svc),
) -> list[SessionOut]:
    infos = await tokens.list_sessions(
        acc.id, current_session_id=getattr(request.state, "auth_session_id", None)
    )
    return [SessionOut.from_info(info) for info in infos]


@router.delete(
    "/me/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("user.profile.edit"))],
    summary="Revoke one of the current user's sessions",
)
async def revoke_my_session(
    request: Request,
    session_id: str,
    acc: UserModel = Depends(get_current_acc),
    tokens: TokenSvc = Depends(get_token_svc),
) -> None:
    if not await tokens.revoke_session(acc.id, session_id, commit=False):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    await audit(
        tokens.session,
        action="user.session.revoke",
        actor_id=acc.id,
        target_type="user",
        target_id=str(acc.id),
        ip=request.client.host if request.client else None,
        meta={"session": "revoked"},
    )
    await tokens.session.commit()


@router.post(
    "/me/sessions/revoke-all",
    response_model=dict[str, int],
    dependencies=[Depends(require_perm("user.profile.edit"))],
    summary="Revoke all current user's sessions",
)
async def revoke_my_sessions(
    request: Request,
    acc: UserModel = Depends(get_current_acc),
    tokens: TokenSvc = Depends(get_token_svc),
) -> dict[str, int]:
    revoked = await tokens.revoke_all_sessions(acc.id, commit=False)
    await audit(
        tokens.session,
        action="user.sessions.revoke_all",
        actor_id=acc.id,
        target_type="user",
        target_id=str(acc.id),
        ip=request.client.host if request.client else None,
        meta={"count": revoked},
    )
    await tokens.session.commit()
    return {"revoked": revoked}


__all__ = ["router"]
