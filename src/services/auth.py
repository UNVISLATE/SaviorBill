from __future__ import annotations

from dataclasses import dataclass
import logging
import hashlib
import hmac
from datetime import datetime, timezone

import valkey.asyncio as valkey
from fastapi import HTTPException, status
from fastapi.security import HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from errors import AuthSessionLimitError
from models.auth_sessions import AuthSessionModel
from models.user import UserModel, UserMngr
from models.system_settings import SystemSettingsMngr
from schemas.auth import TokenPair
from core.config import AppConfig
from utils.datetime_utils import timestamp_now
from utils.degrade import VALKEY_ERRORS, note_degraded
from security.sec import jwt as jwtu
from telemetry.metrics import refresh_token_reuse_total

_bearer = HTTPBearer(auto_error=False)

_DENY = "auth:deny:"  # Префикс ключей денлиста отозванных refresh-jti в Valkey.
_SESSION = "session:"  # Префикс ключей активных сессий: session:{account_id}:{jti}
_SESSION_TTL_DEFAULT = 86400  # 1 день — см. настройку session.ttl.
_CONSUME_REFRESH_SCRIPT = """
if redis.call("EXISTS", KEYS[1]) == 1 then
  return 0
end
redis.call("SET", KEYS[1], "1", "EX", ARGV[1])
return 1
"""

log = logging.getLogger("saviorbill.auth")


@dataclass(slots=True)
class SessionInfo:
    """Активная сессия (одна пара refresh-токена) для одного аккаунта."""

    session_id: str
    ip: str | None
    user_agent: str | None
    created_at: int
    last_seen_at: int
    exp: int
    is_current: bool = False


class TokenSvc:
    """Выпуск/ротация/отзыв JWT с денлистом refresh в Valkey."""

    def __init__(
        self,
        cfg: AppConfig,
        vk: valkey.Valkey,
        settings: SystemSettingsMngr | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        self.cfg = cfg
        self.vk = vk
        self.settings = settings
        self.session = session

    def _access(self, acc: UserModel, session_id: str | None = None) -> str:
        extra = {"login": acc.login, "role": acc.role.name if acc.role else None}
        if session_id is not None:
            extra["sid"] = session_id
        return jwtu.make_access(
            str(acc.id),
            self.cfg.JWT_PRIVATE_KEY,
            self.cfg.JWT_ALG,
            self.cfg.ACCESS_TOKEN_TTL,
            self.cfg.JWT_ISS,
            self.cfg.JWT_KID,
            extra=extra,
        )

    def _refresh(self, acc: UserModel) -> str:
        return jwtu.make_refresh(
            str(acc.id),
            self.cfg.JWT_PRIVATE_KEY,
            self.cfg.JWT_ALG,
            self.cfg.REFRESH_TOKEN_TTL,
            self.cfg.JWT_ISS,
            self.cfg.JWT_KID,
            session_version=getattr(acc, "auth_session_version", 0),
        )

    def issue(
        self,
        acc: UserModel,
    ) -> TokenPair:
        """Выпустить новую пару токенов."""
        refresh_token = self._refresh(acc)
        session_id = None
        if getattr(self.cfg, "AUTH_SESSION_HASH_KEY", None):
            session_id = self._session_digest(self._decode_refresh(refresh_token).jti)
        return TokenPair(
            access_token=self._access(acc, session_id),
            refresh_token=refresh_token,
            expires_in=self.cfg.ACCESS_TOKEN_TTL,
            is_active=acc.is_active,
        )

    async def issue_tracked(
        self,
        acc: UserModel,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> TokenPair:
        """Выпустить пару токенов и завести запись об активной сессии.

        Трекинг сессии вспомогательный: при недоступности Valkey токены всё
        равно выдаются, иначе падение кэша полностью закрывает вход. Отзыв
        refresh-токенов (``revoke``/``is_revoked``) остаётся fail-closed.
        """
        pair = self.issue(acc)
        try:
            claims = self._decode_refresh(pair.refresh_token)
            now = timestamp_now()
            await self._save_session(
                acc.id, claims, ip=ip, user_agent=user_agent, created_at=now
            )
        except VALKEY_ERRORS as exc:
            note_degraded("session_tracking", exc)
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
        if self.session is not None:
            now = datetime.now(timezone.utc)
            max_active = await self._session_max_active()
            account = await self.session.scalar(
                select(UserModel)
                .where(UserModel.id == account_id)
                .with_for_update(of=UserModel)
            )
            if account is None:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account unavailable")
            active_count = await self.session.scalar(
                select(func.count(AuthSessionModel.id)).where(
                    AuthSessionModel.account_id == account_id,
                    AuthSessionModel.revoked_at.is_(None),
                    AuthSessionModel.expires_at > now,
                )
            )
            if max_active is not None and int(active_count or 0) >= max_active:
                raise AuthSessionLimitError
            digest = self._session_digest(claims.jti)
            self.session.add(
                AuthSessionModel(
                    account_id=account_id,
                    refresh_jti_hash=digest,
                    created_at=now,
                    last_seen_at=now,
                    expires_at=datetime.fromtimestamp(claims.exp, tz=timezone.utc),
                    ip=ip,
                    user_agent=user_agent,
                    session_version=int(getattr(account, "auth_session_version", 0)),
                )
            )
            await self.session.commit()
            return
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

    async def _session_max_active(self) -> int | None:
        if self.settings is None:
            return None
        value = await self.settings.get_int("session.max_active", None)
        if value is not None and value < 1:
            raise ValueError("session.max_active must be positive")
        return value

    def _session_digest(self, jti: str) -> str:
        key = getattr(self.cfg, "AUTH_SESSION_HASH_KEY", None)
        if not key:
            raise RuntimeError("AUTH_SESSION_HASH_KEY is required for durable sessions")
        return hmac.new(
            key.encode("utf-8"), jti.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _refresh_claim_cache_key(self, digest: str, session_version: int) -> str:
        return f"{_DENY}v{session_version}:{digest}"

    async def _mark_refresh_claim_used(
        self, digest: str, session_version: int, exp: int
    ) -> None:
        ttl = max(exp - timestamp_now(), 1)
        try:
            await self.vk.set(
                self._refresh_claim_cache_key(digest, session_version),
                "1",
                ex=ttl,
            )
        except VALKEY_ERRORS as exc:
            note_degraded("auth_refresh_negative_cache", exc)

    async def _drop_session(self, account_id: int, jti: str) -> None:
        await self.vk.delete(f"{_SESSION}{account_id}:{jti}")

    async def list_sessions(
        self, account_id: int, current_session_id: str | None = None
    ) -> list[SessionInfo]:
        """Активные сессии аккаунта (данные истекают вместе с TTL сессии)."""
        if self.session is not None:
            now = datetime.now(timezone.utc)
            rows = await self.session.scalars(
                select(AuthSessionModel)
                .where(
                    AuthSessionModel.account_id == account_id,
                    AuthSessionModel.revoked_at.is_(None),
                    AuthSessionModel.expires_at > now,
                )
                .order_by(AuthSessionModel.last_seen_at.desc())
            )
            return [
                SessionInfo(
                    # This is an opaque public handle, never the JWT jti.
                    session_id=row.refresh_jti_hash,
                    ip=row.ip,
                    user_agent=row.user_agent,
                    created_at=int(row.created_at.timestamp()),
                    last_seen_at=int(row.last_seen_at.timestamp()),
                    exp=int(row.expires_at.timestamp()),
                    is_current=row.refresh_jti_hash == current_session_id,
                )
                for row in rows
            ]
        out: list[SessionInfo] = []
        prefix = f"{_SESSION}{account_id}:"
        async for key in self.vk.scan_iter(match=prefix + "*"):
            data = await self.vk.hgetall(key)
            if not data:
                continue
            jti = key.split(":", 2)[2] if isinstance(key, str) else key
            out.append(
                SessionInfo(
                    session_id=jti,
                    ip=data.get("ip") or None,
                    user_agent=data.get("user_agent") or None,
                    created_at=int(data.get("created_at", 0)),
                    last_seen_at=int(data.get("last_seen_at", 0)),
                    exp=int(data.get("exp", 0)),
                )
            )
        out.sort(key=lambda s: s.last_seen_at, reverse=True)
        return out

    async def revoke_session(
        self, account_id: int, jti: str, *, commit: bool = True
    ) -> bool:
        """Принудительно завершить сессию: денлист jti + удаление записи."""
        if self.session is not None:
            digest = jti if len(jti) == 64 else self._session_digest(jti)
            row = await self.session.scalar(
                select(AuthSessionModel)
                .where(
                    AuthSessionModel.account_id == account_id,
                    AuthSessionModel.refresh_jti_hash == digest,
                    AuthSessionModel.revoked_at.is_(None),
                )
                .with_for_update()
            )
            if row is None:
                return False
            row.revoked_at = datetime.now(timezone.utc)
            row.revoke_reason = "manual"
            if commit:
                await self.session.commit()
                await self._mark_refresh_claim_used(
                    row.refresh_jti_hash, row.session_version, int(row.expires_at.timestamp())
                )
            return True
        key = f"{_SESSION}{account_id}:{jti}"
        data = await self.vk.hgetall(key)
        if not data:
            return False
        exp = int(data.get("exp", 0))
        ttl = max(exp - timestamp_now(), 1)
        await self.vk.set(_DENY + jti, "1", ex=ttl)
        await self.vk.delete(key)
        return True

    async def revoke_all_sessions(
        self, account_id: int, *, commit: bool = True
    ) -> int:
        """Завершить все сессии аккаунта (смена пароля, роли, бан).

        Отзываются refresh-токены: выданный ранее access живёт до своего
        короткого TTL, но прав он не даёт — RBAC на каждом запросе читает роль
        из БД, так что бан вступает в силу сразу.

        :return: сколько сессий было отозвано.
        """
        if self.session is not None:
            now = datetime.now(timezone.utc)
            account = await self.session.scalar(
                select(UserModel)
                .where(UserModel.id == account_id)
                .with_for_update(of=UserModel)
            )
            if account is None:
                return 0
            account.auth_session_version = (
                getattr(account, "auth_session_version", 0) + 1
            )
            rows = list(
                (
                    await self.session.scalars(
                        select(AuthSessionModel).where(
                            AuthSessionModel.account_id == account_id,
                            AuthSessionModel.revoked_at.is_(None),
                            AuthSessionModel.expires_at > now,
                        )
                    )
                ).all()
            )
            for row in rows:
                row.revoked_at = now
                row.revoke_reason = "all"
            if commit:
                await self.session.commit()
            return len(rows)

        revoked = 0
        prefix = f"{_SESSION}{account_id}:"
        async for key in self.vk.scan_iter(match=prefix + "*"):
            jti = key.split(":", 2)[2] if isinstance(key, str) else key
            if await self.revoke_session(account_id, jti):
                revoked += 1
        return revoked

    def _decode_refresh(self, token: str) -> jwtu.JWTToken:
        claims = jwtu.decode_jwt(
            token, self.cfg.jwt_public_keys(), self.cfg.JWT_ALG, self.cfg.JWT_ISS
        )
        if claims.typ != jwtu.REFRESH:
            raise jwtu.InvalidJWT("a refresh token was expected")
        return claims

    async def revoke(self, claims: jwtu.JWTToken, account_id: int | None = None) -> None:
        """Занести refresh-jti в денлист до его естественного истечения."""
        if self.session is not None and account_id is not None:
            digest = self._session_digest(claims.jti)
            row = await self.session.scalar(
                select(AuthSessionModel)
                .where(
                    AuthSessionModel.account_id == account_id,
                    AuthSessionModel.refresh_jti_hash
                    == digest,
                    AuthSessionModel.revoked_at.is_(None),
                )
                .with_for_update()
            )
            if row is not None:
                row.revoked_at = datetime.now(timezone.utc)
                row.revoke_reason = "logout"
                await self.session.commit()
                await self._mark_refresh_claim_used(
                    digest, row.session_version, claims.exp
                )
            return
        ttl = max(claims.exp - timestamp_now(), 1)
        await self.vk.set(_DENY + claims.jti, "1", ex=ttl)
        if account_id is not None:
            await self._drop_session(account_id, claims.jti)

    async def is_revoked(self, jti: str) -> bool:
        return bool(await self.vk.exists(_DENY + jti))

    async def _consume_refresh(self, claims: jwtu.JWTToken) -> bool:
        """Atomically reject a previously consumed refresh jti."""
        ttl = max(claims.exp - timestamp_now(), 1)
        return bool(
            await self.vk.eval(
                _CONSUME_REFRESH_SCRIPT,
                1,
                _DENY + claims.jti,
                str(ttl),
            )
        )

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
        if self.session is not None:
            return await self._rotate_durable(
                claims, mngr, ip=ip, user_agent=user_agent
            )
        if not await self._consume_refresh(claims):
            refresh_token_reuse_total.inc()
            log.warning("refresh token reuse rejected for account=%s", claims.sub)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token revoked")

        acc = await mngr.by_id(int(claims.sub))
        if acc is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account unavailable")
        if int(claims.extra.get("session_version", 0)) != getattr(
            acc, "auth_session_version", 0
        ):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token revoked")
        if acc.role is not None and not acc.role.allow_login:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "login not allowed for this role")

        # Перенести created_at старой сессии на новую запись (та же "сессия"
        # с точки зрения пользователя, просто новый jti после ротации).
        old_session = await self.vk.hgetall(f"{_SESSION}{acc.id}:{claims.jti}")
        created_at = (
            int(old_session["created_at"])
            if old_session and "created_at" in old_session
            else timestamp_now()
        )

        await self._drop_session(acc.id, claims.jti)
        pair = self.issue(acc)
        new_claims = self._decode_refresh(pair.refresh_token)
        await self._save_session(
            acc.id, new_claims, ip=ip, user_agent=user_agent, created_at=created_at
        )
        return acc, pair

    async def _rotate_durable(
        self,
        claims: jwtu.JWTToken,
        mngr: UserMngr,
        ip: str | None,
        user_agent: str | None,
    ) -> tuple[UserModel, TokenPair]:
        digest = self._session_digest(claims.jti)
        session_version = int(claims.extra.get("session_version", 0))
        try:
            if await self.vk.exists(
                self._refresh_claim_cache_key(digest, session_version)
            ):
                refresh_token_reuse_total.inc()
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token revoked")
        except VALKEY_ERRORS as exc:
            note_degraded("auth_refresh_negative_cache", exc)
        acc = await mngr.by_id(int(claims.sub))
        if acc is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account unavailable")
        if int(claims.extra.get("session_version", 0)) != getattr(
            acc, "auth_session_version", 0
        ):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token revoked")
        old = await self.session.scalar(
            select(AuthSessionModel)
            .where(
                AuthSessionModel.account_id == acc.id,
                AuthSessionModel.refresh_jti_hash == digest,
                AuthSessionModel.revoked_at.is_(None),
                AuthSessionModel.expires_at > datetime.now(timezone.utc),
            )
            .with_for_update()
        )
        if old is None:
            refresh_token_reuse_total.inc()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token revoked")
        if acc.role is not None and not acc.role.allow_login:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "login not allowed for this role"
            )
        pair = self.issue(acc)
        new_claims = self._decode_refresh(pair.refresh_token)
        now = datetime.now(timezone.utc)
        old.revoked_at = now
        old.revoke_reason = "rotated"
        old.last_seen_at = now
        new = AuthSessionModel(
            account_id=acc.id,
            refresh_jti_hash=self._session_digest(new_claims.jti),
            created_at=old.created_at,
            last_seen_at=now,
            expires_at=datetime.fromtimestamp(new_claims.exp, tz=timezone.utc),
            ip=ip,
            user_agent=user_agent,
            session_version=getattr(acc, "auth_session_version", 0),
        )
        self.session.add(new)
        await self.session.flush()
        old.replaced_by_id = new.id
        await self.session.commit()
        await self._mark_refresh_claim_used(digest, session_version, claims.exp)
        return acc, pair


__all__ = [
    "TokenSvc",
    "SessionInfo",
]
