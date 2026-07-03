"""Валидация access-JWT (общий секрет с billing)."""

from __future__ import annotations

import jwt

ACCESS = "access"


class InvalidToken(Exception):
    """Токен невалиден, просрочен или не является access-токеном."""


def account_id(token: str, secret: str, alg: str, iss: str) -> int:
    """Проверить access-JWT и вернуть идентификатор аккаунта (claim ``sub``).

    :raises InvalidToken: подпись/срок/тип неверны.
    """
    try:
        data = jwt.decode(
            token,
            secret,
            algorithms=[alg],
            issuer=iss,
            options={"require": ["exp", "iat", "sub", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
    if data.get("typ", ACCESS) != ACCESS:
        raise InvalidToken("access token expected")
    try:
        return int(data["sub"])
    except (TypeError, ValueError) as exc:
        raise InvalidToken("bad subject") from exc


__all__ = ["account_id", "InvalidToken", "ACCESS"]
