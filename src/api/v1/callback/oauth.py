"""Колбэк OAuth-провайдера: обмен кода через Lua, привязка аккаунта, токены."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from dependencies.auth import TokenSvc, get_token_svc
from dependencies.oauth import OAuthSvc, get_oauth_svc
from models.user import UserModel
from schemas.auth import TokenPair
from schemas.lua import LuaRequest

router = APIRouter(prefix="/api/v1/callback/oauth", tags=["callback"])


def _build_request(request: Request) -> LuaRequest:
    """Собрать :class:`LuaRequest` из редиректа провайдера (метод/ip/query)."""
    return LuaRequest.build(
        method=request.method,
        ip=request.client.host if request.client else None,
        headers={k.lower(): v for k, v in request.headers.items()},
        query=dict(request.query_params),
        body={},
    )


@router.get(
    "/{provider}",
    response_model=TokenPair,
    summary="Колбэк OAuth",
    description=(
        "Принимает редирект провайдера (code + state). auth-скрипт провайдера "
        "обменивает код на профиль. Если старт был инициирован вошедшим "
        "пользователем — учётка привязывается к его аккаунту; иначе аккаунт "
        "находится/создаётся. Подтверждённый email провайдера верифицирует аккаунт.\n\n"
        "- `code`: код авторизации от провайдера (обязательно)\n"
        "- `state`: антифрод-метка, выданная на старте (обязательно)"
    ),
)
async def oauth_callback(
    provider: str,
    request: Request,
    code: str = Query(..., description="Код авторизации от провайдера (обязательно)"),
    state: str = Query(..., description="Антифрод-метка со старта (обязательно)"),
    svc: OAuthSvc = Depends(get_oauth_svc),
    tokens: TokenSvc = Depends(get_token_svc),
) -> TokenPair:
    user, account_id = await svc.finish(provider, code, state, _build_request(request))
    if account_id is not None:
        acc = await svc.s.get(UserModel, account_id)
        if acc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "аккаунт не найден")
        await svc.link_to_existing(acc, provider, user)
    else:
        acc = await svc.link_account(provider, user)
    await svc.s.commit()
    return tokens.issue(acc)


__all__ = ["router"]
