"""Валидация access-JWT (публичный RS256-ключ, общий с billing).

``ALLOWED_ALGS``/``AUDIENCE`` дублируют значения ``security/sec/jwt.py`` из
billing буквально (по значению, не по импорту — mediaworker — отдельный
деплоймент без общего пакета с billing). При изменении значений в billing
нужно поменять и здесь, иначе токены перестанут проверяться.

mediaworker получает только публичный ключ (см. AUDIT.md, Phase 1) — приватный
ключ живёт в billing-only volume и никогда не монтируется сюда.
"""

from __future__ import annotations

import jwt

ACCESS = "access"

# См. security/sec/jwt.py::ALLOWED_ALGS/AUDIENCE (billing) — держать в синхроне.
ALLOWED_ALGS = frozenset({"RS256", "RS384", "RS512"})
AUDIENCE = "saviorbill-services"


class InvalidToken(Exception):
    """Токен невалиден, просрочен, не является access-токеном или использует
    неразрешённый алгоритм."""


def account_id(token: str, public_keys: dict[str, str], alg: str, iss: str) -> int:
    """Проверить access-JWT и вернуть идентификатор аккаунта (claim ``sub``).

    :arg public_keys: key ring billing ``{kid: публичный_ключ_PEM}`` (не секрет).
    :raises InvalidToken: подпись/срок/тип/алгоритм/аудитория/kid неверны.
    """
    if alg not in ALLOWED_ALGS:
        raise InvalidToken(f"алгоритм {alg!r} не в allowlist {sorted(ALLOWED_ALGS)}")
    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
    if not kid or kid not in public_keys:
        raise InvalidToken(f"неизвестный kid {kid!r}")
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
        raise InvalidToken(str(exc)) from exc
    if data["typ"] != ACCESS:
        raise InvalidToken("access token expected")
    try:
        return int(data["sub"])
    except (TypeError, ValueError) as exc:
        raise InvalidToken("bad subject") from exc


__all__ = ["account_id", "InvalidToken", "ACCESS", "ALLOWED_ALGS", "AUDIENCE"]
