"""Двухфакторная аутентификация: TOTP и коды восстановления (AUDIT.md §1.5)."""

from __future__ import annotations

from types import SimpleNamespace

import pyotp
import pytest

from services.twofa import TotpSvc

pytestmark = pytest.mark.unit


class _Box:
    """Прозрачный SecBox — шифрование проверяется отдельными тестами."""

    def seal(self, value):
        return "enc:" + value

    def open(self, value):
        return value.removeprefix("enc:")


def _acc():
    return SimpleNamespace(
        id=1, login="alice", totp_secret=None, totp_enabled=False, totp_recovery=[]
    )


def test_setup_does_not_enable_until_confirmed():
    acc, svc = _acc(), TotpSvc(_Box())
    secret, uri = svc.start_enrollment(acc, issuer="Shop")
    assert acc.totp_secret and acc.totp_enabled is False
    assert uri.startswith("otpauth://totp/") and "Shop" in uri
    assert secret


def test_enable_requires_a_valid_code():
    acc, svc = _acc(), TotpSvc(_Box())
    svc.start_enrollment(acc)
    with pytest.raises(ValueError):
        svc.enable(acc, "000000")
    assert acc.totp_enabled is False


def test_enable_returns_recovery_codes_and_stores_only_hashes():
    acc, svc = _acc(), TotpSvc(_Box())
    secret, _ = svc.start_enrollment(acc)
    codes = svc.enable(acc, pyotp.TOTP(secret).now())
    assert acc.totp_enabled is True
    assert len(codes) == len(acc.totp_recovery) == 8
    for code in codes:
        assert code not in acc.totp_recovery  # хранится только хэш


def test_recovery_code_works_once():
    acc, svc = _acc(), TotpSvc(_Box())
    secret, _ = svc.start_enrollment(acc)
    codes = svc.enable(acc, pyotp.TOTP(secret).now())

    assert svc.verify_any(acc, codes[0]) is True
    assert svc.verify_any(acc, codes[0]) is False  # погашен
    assert len(acc.totp_recovery) == 7


def test_authenticator_code_is_accepted():
    acc, svc = _acc(), TotpSvc(_Box())
    secret, _ = svc.start_enrollment(acc)
    svc.enable(acc, pyotp.TOTP(secret).now())
    assert svc.verify_code(acc, pyotp.TOTP(secret).now()) is True
    assert svc.verify_code(acc, "123456") is False


def test_code_with_spaces_is_normalised():
    acc, svc = _acc(), TotpSvc(_Box())
    secret, _ = svc.start_enrollment(acc)
    code = pyotp.TOTP(secret).now()
    assert svc.verify_code(acc, f" {code[:3]} {code[3:]} ") is True


def test_disable_clears_every_factor():
    acc, svc = _acc(), TotpSvc(_Box())
    secret, _ = svc.start_enrollment(acc)
    svc.enable(acc, pyotp.TOTP(secret).now())
    svc.disable(acc)
    assert acc.totp_enabled is False
    assert acc.totp_secret is None and acc.totp_recovery == []
    assert svc.verify_code(acc, pyotp.TOTP(secret).now()) is False


def test_account_without_secret_never_verifies():
    assert TotpSvc(_Box()).verify_any(_acc(), "123456") is False
