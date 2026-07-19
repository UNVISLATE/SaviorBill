"""Валидация access-JWT (общий секрет и allowlist алгоритмов с billing).

``ALLOWED_ALGS``/``AUDIENCE`` дублируют значения ``security/sec/jwt.py`` из
billing буквально (по значению, не по импорту — mediaworker — отдельный
деплоймент без общего пакета с billing). При изменении значений в billing
нужно поменять и здесь, иначе токены перестанут проверяться.
"""

from __future__ import annotations

import jwt

ACCESS = "access"

# См. security/sec/jwt.py::ALLOWED_ALGS/AUDIENCE (billing) — держать в синхроне.
ALLOWED_ALGS = frozenset({"HS256", "HS384", "HS512"})
AUDIENCE = "saviorbill-services"


class InvalidToken(Exception):
    """Токен невалиден, просрочен, не является access-токеном или использует
    неразрешённый алгоритм."""


def account_id(token: str, secret: str, alg: str, iss: str) -> int:
    """Проверить access-JWT и вернуть идентификатор аккаунта (claim ``sub``).

    :raises InvalidToken: подпись/срок/тип/алгоритм/аудитория неверны.
    """
    if alg not in ALLOWED_ALGS:
        raise InvalidToken(f"алгоритм {alg!r} не в allowlist {sorted(ALLOWED_ALGS)}")
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
        raise InvalidToken(str(exc)) from exc
    if data.get("typ", ACCESS) != ACCESS:
        raise InvalidToken("access token expected")
    try:
        return int(data["sub"])
    except (TypeError, ValueError) as exc:
        raise InvalidToken("bad subject") from exc


__all__ = ["account_id", "InvalidToken", "ACCESS", "ALLOWED_ALGS", "AUDIENCE"]
