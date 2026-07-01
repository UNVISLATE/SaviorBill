"""Локальная авторизация: регистрация, вход, refresh, профиль, выход."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from dependencies.auth import (
    UserMngr,
    TokenSvc,
    get_acc_mngr,
    get_token_svc,
)
from dependencies.ratelimit import LimitKind, rate_limit
from dependencies.triggers import get_dispatcher
from integrations.triggers import TriggerDispatcher, TriggerEvent
from schemas.auth import Login, Refresh, Reg, TokenPair
from utils.apidoc import with_fields
from utils.sec import jwt as jwtu
from utils.sec.pwd import hash_pass, needs_rehash, verify_pass

router = APIRouter()


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация локального аккаунта",
    description=with_fields(
        "Создаёт локальный аккаунт и сразу выдаёт пару токенов (access/refresh). "
        "Логин и email должны быть свободны. Если передан реферальный код "
        "существующего пользователя — новый аккаунт привязывается к нему как "
        "приглашённый.",
        Reg,
    ),
    dependencies=[Depends(rate_limit("auth.register", LimitKind.AUTH))],
)
async def register(
    body: Reg,
    mngr: UserMngr = Depends(get_acc_mngr),
    tokens: TokenSvc = Depends(get_token_svc),
    triggers: TriggerDispatcher = Depends(get_dispatcher),
) -> TokenPair:
    """Создать локальный аккаунт и сразу выдать токены."""
    if await mngr.by_login(body.login):
        raise HTTPException(status.HTTP_409_CONFLICT, "логин занят")
    if body.email and await mngr.by_email(body.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "email занят")

    acc = await mngr.create(
        body.login, hash_pass(body.password), body.email, ref_by=body.ref_code
    )
    await mngr.s.commit()

    # Триггеры регистрации (best-effort, не ломают регистрацию).
    await triggers.fire(
        TriggerEvent.USER_REGISTERED,
        {"user": {"id": acc.id, "login": acc.login, "email": acc.email}},
    )
    return tokens.issue(acc)


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Вход по логину и паролю",
    description=with_fields(
        "Проверяет логин/пароль и выдаёт новую пару токенов. Заблокированный "
        "аккаунт (роль banned) получает 403.",
        Login,
    ),
    dependencies=[Depends(rate_limit("auth.login", LimitKind.AUTH))],
)
async def login(
    body: Login,
    mngr: UserMngr = Depends(get_acc_mngr),
    tokens: TokenSvc = Depends(get_token_svc),
) -> TokenPair:
    """Вход по логину/паролю."""
    acc = await mngr.by_login(body.login)
    if acc is None or not acc.has_pass or not verify_pass(acc.pass_hash, body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "неверный логин или пароль")
    if not acc.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "аккаунт заблокирован")

    if needs_rehash(acc.pass_hash):
        acc.pass_hash = hash_pass(body.password)
    await mngr.touch_login(acc)
    await mngr.s.commit()
    return tokens.issue(acc)


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Ротация пары токенов",
    description=with_fields(
        "Выдаёт новую пару токенов по действующему refresh-токену; старый "
        "refresh-токен отзывается.",
        Refresh,
    ),
    dependencies=[Depends(rate_limit("auth.refresh", LimitKind.AUTH))],
)
async def refresh(
    body: Refresh,
    mngr: UserMngr = Depends(get_acc_mngr),
    tokens: TokenSvc = Depends(get_token_svc),
) -> TokenPair:
    """Ротация пары токенов по refresh-токену."""
    _, pair = await tokens.rotate(body.refresh_token, mngr)
    return pair


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Выход (отзыв refresh-токена)",
    description=with_fields(
        "Отзывает переданный refresh-токен. Возвращает 204 даже если токен уже "
        "недействителен (идемпотентно).",
        Refresh,
    ),
)
async def logout(
    body: Refresh,
    tokens: TokenSvc = Depends(get_token_svc),
) -> None:
    """Отозвать refresh-токен"""
    try:
        claims = jwtu.decode_jwt(
            body.refresh_token,
            tokens.cfg.JWT_SECRET,
            tokens.cfg.JWT_ALG,
            tokens.cfg.JWT_ISS,
        )
    except jwtu.InvalidJWT:
        return
    if claims.typ == jwtu.REFRESH:
        await tokens.revoke(claims)


__all__ = ["router"]
