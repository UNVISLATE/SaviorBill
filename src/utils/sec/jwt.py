from __future__ import annotations

import uuid
from dataclasses import dataclass

import jwt

from utils.datetime_utils import timestamp_now

ACCESS = "access"
REFRESH = "refresh"


@dataclass(slots=True)
class JWTToken:
    sub: str
    typ: str
    jti: str
    exp: int
    iat: int
    iss: str
    extra: dict


class InvalidJWT(Exception):
    """Токен невалиден, просрочен или подделан."""


def _encode(
    sub: str,
    typ: str,
    secret: str,
    alg: str,
    ttl: int,
    iss: str,
    extra: dict | None = None,
) -> str:
    now = timestamp_now()
    payload: dict = {
        "sub": str(sub),
        "typ": typ,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + ttl,
        "iss": iss,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, secret, algorithm=alg)


def make_access(
    sub: str, secret: str, alg: str, ttl: int, iss: str, extra: dict | None = None
) -> str:
    """Короткоживущий access-токен."""
    return _encode(sub, ACCESS, secret, alg, ttl, iss, extra)


def make_refresh(sub: str, secret: str, alg: str, ttl: int, iss: str) -> str:
    """Долгоживущий refresh-токен (только sub, без полезной нагрузки)."""
    return _encode(sub, REFRESH, secret, alg, ttl, iss)


def decode_jwt(token: str, secret: str, alg: str, iss: str) -> JWTToken:
    """Декодировать и провалидировать токен. Бросает ``InvalidJWT`` при ошибке."""
    try:
        data = jwt.decode(
            token,
            secret,
            algorithms=[alg],
            issuer=iss,
            options={"require": ["exp", "iat", "sub", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidJWT(str(exc)) from exc

    reserved = {"sub", "typ", "jti", "exp", "iat", "iss"}
    return JWTToken(
        sub=data["sub"],
        typ=data.get("typ", ACCESS),
        jti=data["jti"],
        exp=data["exp"],
        iat=data["iat"],
        iss=data.get("iss", iss),
        extra={k: v for k, v in data.items() if k not in reserved},
    )


__all__ = [
    "ACCESS",
    "REFRESH",
    "JWTToken",
    "InvalidJWT",
    "make_access",
    "make_refresh",
    "decode_jwt",
]
