"""Юнит-тесты HMAC-подписи шины Valkey Streams (AUDIT.md H1)."""

from __future__ import annotations

import time

import pytest

from security.sec.bus_sign import sign_fields, verify_fields

pytestmark = pytest.mark.unit


def test_roundtrip_sign_then_verify():
    signed = sign_fields("shared-secret", {"cid": "abc", "kind": "invoice.create"})
    assert "ts" in signed and "sig" in signed
    assert verify_fields("shared-secret", signed) is True


def test_tampered_field_rejected():
    signed = sign_fields("shared-secret", {"cid": "abc", "kind": "invoice.create"})
    tampered = dict(signed, kind="invoice.delete")
    assert verify_fields("shared-secret", tampered) is False


def test_wrong_key_rejected():
    signed = sign_fields("key-a", {"cid": "abc"})
    assert verify_fields("key-b", signed) is False


def test_missing_sig_or_ts_rejected():
    assert verify_fields("shared-secret", {"cid": "abc"}) is False
    assert verify_fields("shared-secret", {"cid": "abc", "sig": "deadbeef"}) is False


def test_expired_ts_rejected_anti_replay():
    signed = sign_fields("shared-secret", {"cid": "abc"})
    signed["ts"] = str(int(time.time()) - 10_000)
    # Пересчитываем подпись под "старым" ts, чтобы проверить именно skew, а не sig-мисматч.
    from security.sec.bus_sign import _canonical
    import hmac
    import hashlib

    signed["sig"] = hmac.new(
        b"shared-secret", _canonical(signed), hashlib.sha256
    ).hexdigest()
    assert verify_fields("shared-secret", signed) is False


def test_disabled_signing_accepts_anything():
    """Пустой key = подпись отключена (dev/тесты без BUS_SIGNING_KEY)."""
    assert sign_fields("", {"cid": "abc"}) == {"cid": "abc"}
    assert verify_fields("", {"cid": "abc"}) is True
    assert verify_fields("", {}) is True
