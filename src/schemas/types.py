"""Общие аннотированные типы полей запросов."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+$")


def normalize_email(value: str | None) -> str | None:
    """Привести email к каноничному виду: без пробелов, в нижнем регистре.

    Валидирует синтаксис адреса и защищает от инъекций (CRLF, разделители).
    """
    if value is None:
        return None
    value = value.strip().lower()
    if not value:
        return None
    if any(c in value for c in "\r\n\t\0"):
        raise ValueError("Invalid email: control characters not allowed")
    if not _EMAIL_RE.match(value) or len(value) > 254:
        raise ValueError("Invalid email address format")
    return value


#: Email, нормализованный на входе. Использовать во всех схемах, которые
#: пишут адрес в БД.
NormEmail = Annotated[str, AfterValidator(normalize_email)]
OptNormEmail = Annotated[str | None, AfterValidator(normalize_email)]

__all__ = ["NormEmail", "OptNormEmail", "normalize_email"]
