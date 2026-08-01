"""Общие аннотированные типы полей запросов."""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator


def normalize_email(value: str | None) -> str | None:
    """Привести email к каноничному виду: без пробелов, в нижнем регистре.

    Регистр домена и локальной части не различается ни одним практически
    используемым почтовым провайдером, а хранение в разном регистре давало два
    аккаунта на один адрес и 500 на уникальном индексе (см. AUDIT.md §2.1).
    """
    if value is None:
        return None
    value = value.strip().lower()
    return value or None


#: Email, нормализованный на входе. Использовать во всех схемах, которые
#: пишут адрес в БД.
NormEmail = Annotated[str, AfterValidator(normalize_email)]
OptNormEmail = Annotated[str | None, AfterValidator(normalize_email)]

__all__ = ["NormEmail", "OptNormEmail", "normalize_email"]
