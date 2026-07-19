"""Локальная авторизация: регистрация, вход, refresh, профиль, выход."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from dependencies.auth import (
    UserMngr,
    TokenSvc,
    get_acc_mngr,
    get_banned_domains_mngr,
    get_token_svc,
)
from dependencies.login_guard import LoginGuard, client_ip, get_login_guard
from dependencies.ratelimit import LimitKind, rate_limit
from dependencies.triggers import get_dispatcher
from lifecycle.triggers import TriggerDispatcher, TriggerEvent
from models.banned_email_domains import BannedEmailDomainsMngr
from schemas.auth import Login, Refresh, Reg, TokenPair
from security.sec import jwt as jwtu
from security.sec.pwd import dummy_hash, hash_pass, needs_rehash, verify_pass

router = APIRouter()


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Register local account",
    description=(
        "Creates a local account and returns access and refresh tokens. If "
        "`ref_code` matches an existing user, the new account is linked as referred."
    ),
    dependencies=[Depends(rate_limit("auth.register", LimitKind.AUTH))],
)
async def register(
    body: Reg,
    mngr: UserMngr = Depends(get_acc_mngr),
    banned_domains: BannedEmailDomainsMngr = Depends(get_banned_domains_mngr),
    tokens: TokenSvc = Depends(get_token_svc),
    triggers: TriggerDispatcher = Depends(get_dispatcher),
) -> TokenPair:
    """Создать локальный аккаунт и сразу выдать токены."""
    if body.email and await banned_domains.is_banned(body.email):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "registration from this email domain is not allowed"
        )
    # Единое сообщение (не раскрывает, что именно занято — логин или email).
    if await mngr.by_login(body.login) or (
        body.email and await mngr.by_email(body.email)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "account already exists")

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
    summary="Login with password",
    description=(
        "Checks login and password and returns access and refresh tokens. "
        "Blocked accounts can still log in but remain restricted by RBAC."
    ),
    dependencies=[Depends(rate_limit("auth.login", LimitKind.AUTH))],
)
async def login(
    body: Login,
    request: Request,
    mngr: UserMngr = Depends(get_acc_mngr),
    tokens: TokenSvc = Depends(get_token_svc),
    guard: LoginGuard = Depends(get_login_guard),
) -> TokenPair:
    """Вход по логину/паролю."""
    ip = client_ip(request)
    # Доп. анти-брутфорс поверх общего rate_limit — блокировка по логину и IP.
    await guard.check(body.login, ip)

    acc = await mngr.by_login_or_email(body.login)
    # Анти-тайминг: путь исполнения (и его длительность) одинаков независимо
    # от существования аккаунта — иначе раннее замыкание раскрывает через
    # разницу во времени ответа, что логин занят (user enumeration).
    pass_hash = acc.pass_hash if (acc is not None and acc.has_pass) else dummy_hash()
    pass_ok = verify_pass(pass_hash, body.password)
    if acc is None or not acc.has_pass or not pass_ok:
        await guard.record_fail(body.login, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid login or password")

    # is_active (бан) больше не блокирует вход — роль banned и так лишена
    # прав через RBAC; клиент получает токены + флаг is_active=false.
    if needs_rehash(acc.pass_hash):
        acc.pass_hash = hash_pass(body.password)
    await mngr.touch_login(acc)
    await mngr.s.commit()
    await guard.clear(body.login)
    return tokens.issue(acc)


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Refresh tokens",
    description="Rotates the refresh token and returns a new token pair.",
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
    summary="Logout",
    description="Revokes the provided refresh token. Returns 204 even if it is already invalid.",
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
