"""Двухфакторная аутентификация (TOTP, RFC 6238).

Секрет хранится зашифрованным (тот же :class:`SecBox`, что и остальные
секреты), коды восстановления — только в виде хэшей: у нас не должно быть
способа предъявить чужой второй фактор.

Обязательность для админов включается настройкой ``auth.2fa.required_for_admin``:
при ней аккаунт с ролью, допущенной в админку, не может делать ничего, кроме
включения 2FA, пока не включит её (см. :func:`dependencies.twofa.require_2fa`).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

import pyotp

from models.user import UserModel
from security.sec.box import SecBox

_ISSUER_FALLBACK = "SaviorBill"
_RECOVERY_CODES = 8
_RECOVERY_BYTES = 5


def _hash_recovery(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def generate_recovery_codes() -> tuple[list[str], list[str]]:
    """Сгенерировать коды восстановления: (открытые, их хэши)."""
    codes = [secrets.token_hex(_RECOVERY_BYTES) for _ in range(_RECOVERY_CODES)]
    return codes, [_hash_recovery(c) for c in codes]


class TotpSvc:
    """Выпуск, проверка и отзыв второго фактора аккаунта."""

    def __init__(self, box: SecBox) -> None:
        self.box = box

    def start_enrollment(self, acc: UserModel, issuer: str | None = None) -> tuple[str, str]:
        """Сгенерировать новый секрет и вернуть ``(секрет, otpauth-URI)``.

        Секрет сохраняется зашифрованным, но ``totp_enabled`` остаётся ``False``
        до подтверждения кодом: иначе неудачная настройка запирала бы аккаунт.
        """
        secret = pyotp.random_base32()
        acc.totp_secret = self.box.seal(secret)
        acc.totp_enabled = False
        uri = pyotp.TOTP(secret).provisioning_uri(
            name=acc.login, issuer_name=issuer or _ISSUER_FALLBACK
        )
        return secret, uri

    def _secret(self, acc: UserModel) -> str | None:
        if not acc.totp_secret:
            return None
        return self.box.open(acc.totp_secret)

    def verify_code(self, acc: UserModel, code: str) -> bool:
        """Проверить код авторизатора (с окном ±1 шаг на расхождение часов)."""
        secret = self._secret(acc)
        if not secret or not code:
            return False
        return pyotp.TOTP(secret).verify(code.strip().replace(" ", ""), valid_window=1)

    @staticmethod
    def consume_recovery(acc: UserModel, code: str) -> bool:
        """Погасить код восстановления (одноразовый)."""
        stored = list(acc.totp_recovery or [])
        if not stored or not code:
            return False
        target = _hash_recovery(code.strip().replace(" ", ""))
        for i, item in enumerate(stored):
            if hmac.compare_digest(str(item), target):
                stored.pop(i)
                acc.totp_recovery = stored
                return True
        return False

    def verify_any(self, acc: UserModel, code: str) -> bool:
        """Принять либо код авторизатора, либо код восстановления."""
        return self.verify_code(acc, code) or self.consume_recovery(acc, code)

    def enable(self, acc: UserModel, code: str) -> list[str]:
        """Подтвердить настройку кодом и включить 2FA.

        :return: коды восстановления (показываются пользователю один раз).
        :raises ValueError: код не подошёл.
        """
        if not self.verify_code(acc, code):
            raise ValueError("invalid code")
        codes, hashes = generate_recovery_codes()
        acc.totp_enabled = True
        acc.totp_recovery = hashes
        return codes

    @staticmethod
    def disable(acc: UserModel) -> None:
        acc.totp_enabled = False
        acc.totp_secret = None
        acc.totp_recovery = []


__all__ = ["TotpSvc", "generate_recovery_codes"]
