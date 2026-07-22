from __future__ import annotations

from dataclasses import dataclass

import valkey.asyncio as valkey
from fastapi import HTTPException, status
from fastapi.security import HTTPBearer

from models.user import UserModel, UserMngr
from models.system_settings import SystemSettingsMngr
from schemas.auth import TokenPair
from core.config import AppConfig
from utils.datetime_utils import timestamp_now
from security.sec import jwt as jwtu

_bearer = HTTPBearer(auto_error=False)

_DENY = "auth:deny:"  # Префикс ключей денлиста отозванных refresh-jti в Valkey.
_SESSION = "session:"  # Префикс ключей активных сессий: session:{account_id}:{jti}
_SESSION_TTL_DEFAULT = 86400  # 1 день — см. настройку session.ttl.


@dataclass(slots=True)
class SessionInfo:
    """Активная сессия (одна пара refresh-токена) для одного аккаунта."""

    jti: str
    ip: str | None
    user_agent: str | None
    created_at: int
    last_seen_at: int
    exp: int


class TokenSvc:
    """Выпуск/ротация/отзыв JWT с денлистом refresh в Valkey."""

    def __init__(
        self,
        cfg: AppConfig,
        vk: valkey.Valkey,
        settings: SystemSettingsMngr | None = None,
    ) -> None:
        self.cfg = cfg
        self.vk = vk
        self.settings = settings

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

    def issue(
        self,
        acc: UserModel,
    ) -> TokenPair:
        """Выпустить новую пару токенов."""
        return TokenPair(
            access_token=self._access(acc),
            refresh_token=self._refresh(acc),
            expires_in=self.cfg.ACCESS_TOKEN_TTL,
            is_active=acc.is_active,
        )

    async def issue_tracked(
        self,
        acc: UserModel,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> TokenPair:
        """Выпустить пару токенов и завести запись об активной сессии."""
        pair = self.issue(acc)
        claims = self._decode_refresh(pair.refresh_token)
        now = timestamp_now()
        await self._save_session(
            acc.id, claims, ip=ip, user_agent=user_agent, created_at=now
        )
        return pair

    async def _session_ttl(self) -> int:
        if self.settings is None:
            return _SESSION_TTL_DEFAULT
        return await self.settings.get_int("session.ttl", _SESSION_TTL_DEFAULT)

    async def _save_session(
        self,
        account_id: int,
        claims: jwtu.JWTToken,
        ip: str | None,
        user_agent: str | None,
        created_at: int,
    ) -> None:
        key = f"{_SESSION}{account_id}:{claims.jti}"
        ttl = min(await self._session_ttl(), max(claims.exp - timestamp_now(), 1))
        await self.vk.hset(
            key,
            mapping={
                "ip": ip or "",
                "user_agent": user_agent or "",
                "created_at": str(created_at),
                "last_seen_at": str(created_at),
                "exp": str(claims.exp),
            },
        )
        await self.vk.expire(key, ttl)

    async def _drop_session(self, account_id: int, jti: str) -> None:
        await self.vk.delete(f"{_SESSION}{account_id}:{jti}")

    async def list_sessions(self, account_id: int) -> list[SessionInfo]:
        """Активные сессии аккаунта (данные истекают вместе с TTL сессии)."""
        out: list[SessionInfo] = []
        prefix = f"{_SESSION}{account_id}:"
        async for key in self.vk.scan_iter(match=prefix + "*"):
            data = await self.vk.hgetall(key)
            if not data:
                continue
            jti = key.split(":", 2)[2] if isinstance(key, str) else key
            out.append(
                SessionInfo(
                    jti=jti,
                    ip=data.get("ip") or None,
                    user_agent=data.get("user_agent") or None,
                    created_at=int(data.get("created_at", 0)),
                    last_seen_at=int(data.get("last_seen_at", 0)),
                    exp=int(data.get("exp", 0)),
                )
            )
        out.sort(key=lambda s: s.last_seen_at, reverse=True)
        return out

    async def revoke_session(self, account_id: int, jti: str) -> bool:
        """Принудительно завершить сессию: денлист jti + удаление записи."""
        key = f"{_SESSION}{account_id}:{jti}"
        data = await self.vk.hgetall(key)
        if not data:
            return False
        exp = int(data.get("exp", 0))
        ttl = max(exp - timestamp_now(), 1)
        await self.vk.set(_DENY + jti, "1", ex=ttl)
        await self.vk.delete(key)
        return True

    def _decode_refresh(self, token: str) -> jwtu.JWTToken:
        claims = jwtu.decode_jwt(
            token, self.cfg.JWT_SECRET, self.cfg.JWT_ALG, self.cfg.JWT_ISS
        )
        if claims.typ != jwtu.REFRESH:
            raise jwtu.InvalidJWT("a refresh token was expected")
        return claims

    async def revoke(self, claims: jwtu.JWTToken, account_id: int | None = None) -> None:
        """Занести refresh-jti в денлист до его естественного истечения."""
        ttl = max(claims.exp - timestamp_now(), 1)
        await self.vk.set(_DENY + claims.jti, "1", ex=ttl)
        if account_id is not None:
            await self._drop_session(account_id, claims.jti)

    async def is_revoked(self, jti: str) -> bool:
        return bool(await self.vk.exists(_DENY + jti))

    async def rotate(
        self,
        refresh_token: str,
        mngr: UserMngr,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[UserModel, TokenPair]:
        """Проверить refresh, отозвать старый, выдать новую пару."""
        try:
            claims = self._decode_refresh(refresh_token)
        except jwtu.InvalidJWT as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
        if await self.is_revoked(claims.jti):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token revoked")

        acc = await mngr.by_id(int(claims.sub))
        if acc is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account unavailable")

        # Перенести created_at старой сессии на новую запись (та же "сессия"
        # с точки зрения пользователя, просто новый jti после ротации).
        old_session = await self.vk.hgetall(f"{_SESSION}{acc.id}:{claims.jti}")
        created_at = (
            int(old_session["created_at"])
            if old_session and "created_at" in old_session
            else timestamp_now()
        )

        await self.revoke(claims, account_id=acc.id)  # старый refresh инвалидирован
        pair = self.issue(acc)
        new_claims = self._decode_refresh(pair.refresh_token)
        await self._save_session(
            acc.id, new_claims, ip=ip, user_agent=user_agent, created_at=created_at
        )
        return acc, pair


__all__ = [
    "TokenSvc",
    "SessionInfo",
]
