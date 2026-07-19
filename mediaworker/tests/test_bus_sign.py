"""Юнит-тесты HMAC-подписи шины Valkey Streams — mediaworker-сторона (AUDIT.md H1)."""

from __future__ import annotations

import hashlib
import hmac
import time

from utils.bus_sign import _canonical, sign_fields, verify_fields


def test_roundtrip_sign_then_verify():
    signed = sign_fields("shared-secret", {"cid": "abc", "op": "convert"})
    assert "ts" in signed and "sig" in signed
    assert verify_fields("shared-secret", signed) is True


def test_tampered_field_rejected():
    signed = sign_fields("shared-secret", {"cid": "abc", "op": "convert"})
    tampered = dict(signed, op="delete")
    assert verify_fields("shared-secret", tampered) is False


def test_wrong_key_rejected():
    signed = sign_fields("key-a", {"cid": "abc"})
    assert verify_fields("key-b", signed) is False


def test_missing_sig_or_ts_rejected():
    assert verify_fields("shared-secret", {"cid": "abc"}) is False


def test_expired_ts_rejected_anti_replay():
    signed = sign_fields("shared-secret", {"cid": "abc"})
    signed["ts"] = str(int(time.time()) - 10_000)
    signed["sig"] = hmac.new(
        b"shared-secret", _canonical(signed), hashlib.sha256
    ).hexdigest()
    assert verify_fields("shared-secret", signed) is False


def test_disabled_signing_accepts_anything():
    assert sign_fields("", {"cid": "abc"}) == {"cid": "abc"}
    assert verify_fields("", {"cid": "abc"}) is True
