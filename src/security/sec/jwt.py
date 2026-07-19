from __future__ import annotations

import uuid
from dataclasses import dataclass

import jwt

from utils.datetime_utils import timestamp_now

ACCESS = "access"
REFRESH = "refresh"

# Жёсткий allowlist алгоритмов — не читается из ``alg`` слепо. Защита от
# alg-confusion и от случайной подмены конфигурации на "none"/асимметричный
# алгоритм, для которого ``secret`` использовался бы как публичный ключ.
# HS-семейство — единственное, что реально используется:
# secret общий между billing и mediaworker (симметричная проверка).
ALLOWED_ALGS = frozenset({"HS256", "HS384", "HS512"})

# Аудитория токенов этого стека — билинг + доверенные внутренние сервисы
# (mediaworker), которые проверяют access-JWT тем же общим secret'ом.
# Явный ``aud`` не даёт токену, случайно/умышленно созданному с тем же
# secret+iss для не-JWT-сессионных целей, быть принятым здесь.
AUDIENCE = "saviorbill-services"


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
    """Токен невалиден, просрочен, подделан или использует неразрешённый алгоритм."""


def _check_alg(alg: str) -> None:
    if alg not in ALLOWED_ALGS:
        raise InvalidJWT(
            f"алгоритм {alg!r} не в allowlist {sorted(ALLOWED_ALGS)}"
        )


def _encode(
    sub: str,
    typ: str,
    secret: str,
    alg: str,
    ttl: int,
    iss: str,
    extra: dict | None = None,
) -> str:
    _check_alg(alg)
    now = timestamp_now()
    payload: dict = {
        "sub": str(sub),
        "typ": typ,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + ttl,
        "iss": iss,
        "aud": AUDIENCE,
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
    _check_alg(alg)
    try:
        data = jwt.decode(
            token,
            secret,
            algorithms=[alg],
            issuer=iss,
            audience=AUDIENCE,
            options={"require": ["exp", "iat", "sub", "jti", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidJWT(str(exc)) from exc

    reserved = {"sub", "typ", "jti", "exp", "iat", "iss", "aud"}
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
    "ALLOWED_ALGS",
    "AUDIENCE",
    "JWTToken",
    "InvalidJWT",
    "make_access",
    "make_refresh",
    "decode_jwt",
]
