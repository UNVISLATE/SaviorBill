from __future__ import annotations

import uuid
from dataclasses import dataclass

import jwt

from utils.datetime_utils import timestamp_now

ACCESS = "access"
REFRESH = "refresh"

# Жёсткий allowlist алгоритмов — не читается из ``alg`` слепо. Защита от
# alg-confusion (в частности — от подмены на симметричный HS, для которого
# публичный ключ можно было бы подсунуть как ``secret``) и от случайной
# подмены конфигурации на "none". Только RS-семейство (асимметрия): billing
# подписывает приватным ключом, mediaworker проверяет access-токены только
# публичным — компрометация mediaworker не даёт подделывать токены billing
# (см. AUDIT.md §1.1).
ALLOWED_ALGS = frozenset({"RS256", "RS384", "RS512"})

# Аудитория токенов этого стека — билинг + доверенные внутренние сервисы
# (mediaworker), которые проверяют access-JWT публичным ключом billing.
# Явный ``aud`` не даёт токену, случайно/умышленно созданному тем же
# ключом+iss для не-JWT-сессионных целей, быть принятым здесь.
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
    private_key: str,
    alg: str,
    ttl: int,
    iss: str,
    kid: str,
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
    return jwt.encode(payload, private_key, algorithm=alg, headers={"kid": kid})


def make_access(
    sub: str,
    private_key: str,
    alg: str,
    ttl: int,
    iss: str,
    kid: str,
    extra: dict | None = None,
) -> str:
    """Короткоживущий access-токен, подписанный приватным ключом billing."""
    return _encode(sub, ACCESS, private_key, alg, ttl, iss, kid, extra)


def make_refresh(
    sub: str,
    private_key: str,
    alg: str,
    ttl: int,
    iss: str,
    kid: str,
    session_version: int = 0,
) -> str:
    """Долгоживущий refresh-токен с версией security-сессий аккаунта."""
    return _encode(
        sub,
        REFRESH,
        private_key,
        alg,
        ttl,
        iss,
        kid,
        extra={"session_version": session_version},
    )


def decode_jwt(token: str, public_keys: dict[str, str], alg: str, iss: str) -> JWTToken:
    """Декодировать и провалидировать токен по key ring ``{kid: публичный_ключ}``.

    Ключ выбирается по заголовку ``kid`` токена — так поддерживается ротация
    ключей без мгновенного logout (см. ``AppConfig.jwt_public_keys``,
    AUDIT.md §1.5). Бросает ``InvalidJWT`` при ошибке или неизвестном ``kid``.
    """
    _check_alg(alg)
    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except jwt.PyJWTError as exc:
        raise InvalidJWT(str(exc)) from exc
    if not kid or kid not in public_keys:
        raise InvalidJWT(f"неизвестный kid {kid!r}")
    try:
        data = jwt.decode(
            token,
            public_keys[kid],
            algorithms=[alg],
            issuer=iss,
            audience=AUDIENCE,
            options={"require": ["exp", "iat", "sub", "jti", "aud", "typ"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidJWT(str(exc)) from exc

    if data["typ"] not in (ACCESS, REFRESH):
        raise InvalidJWT(f"неизвестный typ {data['typ']!r}")

    reserved = {"sub", "typ", "jti", "exp", "iat", "iss", "aud"}
    return JWTToken(
        sub=data["sub"],
        typ=data["typ"],
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
