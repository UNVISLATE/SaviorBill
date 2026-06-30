from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import HTTPException, status
from fastapi.security import HTTPBearer

from models.user import UserModel, UserMngr
from schemas.auth import TokenPair
from utils.config import AppConfig
from utils.datetime_utils import timestamp_now
from utils.sec import jwt as jwtu

_bearer = HTTPBearer(auto_error=False)

_DENY = "auth:deny:"  # Префикс ключей денлиста отозванных refresh-jti в Valkey.


class TokenSvc:
    """Выпуск/ротация/отзыв JWT с денлистом refresh в Valkey."""

    def __init__(self, cfg: AppConfig, vk: valkey.Valkey) -> None:
        self.cfg = cfg
        self.vk = vk

    def _access(self, acc: UserModel) -> str:
        return jwtu.make_access(
            str(acc.id),
            self.cfg.JWT_SECRET,
            self.cfg.JWT_ALG,
            self.cfg.ACCESS_TOKEN_TTL,
            self.cfg.JWT_ISS,
            extra={"login": acc.login, "role": acc.role.name if acc.role else None},
        )

    def _refresh(self, acc: UserModel) -> str:
        return jwtu.make_refresh(
            str(acc.id),
            self.cfg.JWT_SECRET,
            self.cfg.JWT_ALG,
            self.cfg.REFRESH_TOKEN_TTL,
            self.cfg.JWT_ISS,
        )

    def issue(self, acc: UserModel) -> TokenPair:
        """Выпустить новую пару токенов."""
        return TokenPair(
            access_token=self._access(acc),
            refresh_token=self._refresh(acc),
            expires_in=self.cfg.ACCESS_TOKEN_TTL,
        )

    def _decode_refresh(self, token: str) -> jwtu.JWTToken:
        claims = jwtu.decode_jwt(
            token, self.cfg.JWT_SECRET, self.cfg.JWT_ALG, self.cfg.JWT_ISS
        )
        if claims.typ != jwtu.REFRESH:
            raise jwtu.InvalidJWT("ожидался refresh-токен")
        return claims

    async def revoke(self, claims: jwtu.JWTToken) -> None:
        """Занести refresh-jti в денлист до его естественного истечения."""
        ttl = max(claims.exp - timestamp_now(), 1)
        await self.vk.set(_DENY + claims.jti, "1", ex=ttl)

    async def is_revoked(self, jti: str) -> bool:
        return bool(await self.vk.exists(_DENY + jti))

    async def rotate(
        self, refresh_token: str, mngr: UserMngr
    ) -> tuple[UserModel, TokenPair]:
        """Проверить refresh, отозвать старый, выдать новую пару."""
        try:
            claims = self._decode_refresh(refresh_token)
        except jwtu.InvalidJWT as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
        if await self.is_revoked(claims.jti):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "токен отозван")

        acc = await mngr.by_id(int(claims.sub))
        if acc is None or not acc.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "аккаунт недоступен")

        await self.revoke(claims)  # ротация: старый refresh больше не валиден
        return acc, self.issue(acc)


__all__ = [
    "TokenSvc",
]
