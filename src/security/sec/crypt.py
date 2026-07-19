"""Генерация одноразовых токенов и числовых кодов подтверждения."""

import secrets


def generate_base_token() -> str:
    """Сгенерировать URL-safe токен (для ссылок/служебных меток).

    :return: случайная строка ~43 символа.
    """
    return secrets.token_urlsafe(32)


def generate_numeric_code(digits: int) -> str:
    """Сгенерировать числовой код фиксированной длины (с ведущими нулями).

    :arg digits: число знаков кода (например 4 или 6).
    :return: строка из ``digits`` цифр.
    """
    if digits < 1:
        raise ValueError("digits должно быть >= 1")
    upper = 10**digits
    return str(secrets.randbelow(upper)).zfill(digits)
