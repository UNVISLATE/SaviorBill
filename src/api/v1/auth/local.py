"""Локальная авторизация: регистрация, вход, refresh, профиль, выход."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from dependencies.auth import (
    AccMngr,
    TokenSvc,
    get_acc_mngr,
    get_token_svc,
)
from schemas.auth import LoginIn, RefreshIn, RegIn, TokenPair
from utils.sec import jwt as jwtu
from utils.sec.pwd import hash_pass, needs_rehash, verify_pass

router = APIRouter()


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegIn,
    mngr: AccMngr = Depends(get_acc_mngr),
    tokens: TokenSvc = Depends(get_token_svc),
) -> TokenPair:
    """Создать локальный аккаунт и сразу выдать токены."""
    if await mngr.by_login(body.login):
        raise HTTPException(status.HTTP_409_CONFLICT, "логин занят")
    if body.email and await mngr.by_email(body.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "email занят")

    acc = await mngr.create(body.login, hash_pass(body.password), body.email)
    await mngr.s.commit()
    return tokens.issue(acc)


@router.post("/login", response_model=TokenPair)
async def login(
    body: LoginIn,
    mngr: AccMngr = Depends(get_acc_mngr),
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


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    body: RefreshIn,
    mngr: AccMngr = Depends(get_acc_mngr),
    tokens: TokenSvc = Depends(get_token_svc),
) -> TokenPair:
    """Ротация пары токенов по refresh-токену."""
    _, pair = await tokens.rotate(body.refresh_token, mngr)
    return pair


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: RefreshIn,
    tokens: TokenSvc = Depends(get_token_svc),
) -> None:
    """Отозвать refresh-токен (добавить в денлист)."""
    try:
        claims = jwtu.decode_jwt(
            body.refresh_token,
            tokens.cfg.JWT_SECRET,
            tokens.cfg.JWT_ALG,
            tokens.cfg.JWT_ISS,
        )
    except jwtu.BadToken:
        return  # просроченный/битый токен отзывать не нужно
    if claims.typ == jwtu.REFRESH:
        await tokens.revoke(claims)


__all__ = ["router"]
