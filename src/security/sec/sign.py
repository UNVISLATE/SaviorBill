import hmac
import hashlib


def sign_data(key: bytes, data: bytes) -> str:
    """Создает HMAC-SHA256 подпись для данных."""
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def verify_signature(key: bytes, data: bytes, signature: str) -> bool:
    """Проверяет HMAC-SHA256 подпись данных."""
    expected_signature = sign_data(key, data)
    return hmac.compare_digest(expected_signature, signature)


__all__ = [
    "sign_data",
    "verify_signature",
]
