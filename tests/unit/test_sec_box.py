"""Юнит-тесты шифрования секретов (SecBox / Fernet)."""

import pytest

from utils.sec.box import SecBox

pytestmark = pytest.mark.unit


def test_plain_mode_roundtrip_without_key():
    box = SecBox(None)
    sealed = box.seal("my-secret")
    assert sealed.startswith("plain:")
    assert box.open(sealed) == "my-secret"


def test_encrypted_roundtrip_with_key():
    box = SecBox(SecBox.new_key())
    sealed = box.seal("my-secret")
    assert sealed.startswith("enc:")
    assert "my-secret" not in sealed  # реально зашифровано
    assert box.open(sealed) == "my-secret"


def test_open_encrypted_without_key_raises():
    sealed = SecBox(SecBox.new_key()).seal("x")
    with pytest.raises(RuntimeError):
        SecBox(None).open(sealed)


def test_wrong_key_raises():
    sealed = SecBox(SecBox.new_key()).seal("x")
    with pytest.raises(RuntimeError):
        SecBox(SecBox.new_key()).open(sealed)


def test_legacy_value_without_prefix_passthrough():
    assert SecBox(None).open("raw-legacy") == "raw-legacy"
