"""Юнит-тесты шифрования секретов (SecBox / Fernet)."""

import pytest

from security.sec.box import SecBox

pytestmark = pytest.mark.unit


def test_seal_without_key_raises():
    # Шифрование обязательно: без ключа seal запрещён (нет plaintext-секретов).
    with pytest.raises(RuntimeError):
        SecBox(None).seal("my-secret")


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


# ─────────────────────────────────────────────────────────────────────────────
# Ротация ключей (IMPLEMENTATION_PLAN §12) — MultiFernet, "vN:key" CSV
# ─────────────────────────────────────────────────────────────────────────────

def test_multi_key_new_reads_old_ciphertext():
    """После добавления нового ключа первым в список старые данные читаемы."""
    old_key = SecBox.new_key()
    sealed = SecBox(old_key).seal("secret-1")

    new_key = SecBox.new_key()
    rotated_box = SecBox(f"v2:{new_key},v1:{old_key}")
    assert rotated_box.open(sealed) == "secret-1"


def test_multi_key_seal_uses_first_key():
    """seal() всегда шифрует новым (первым) ключом — старый больше не нужен для записи."""
    old_key = SecBox.new_key()
    new_key = SecBox.new_key()
    rotated_box = SecBox(f"v2:{new_key},v1:{old_key}")

    sealed = rotated_box.seal("secret-2")

    # Ключ, состоящий только из старого, больше не может расшифровать новые данные.
    with pytest.raises(RuntimeError):
        SecBox(old_key).open(sealed)
    # Только новый ключ (или список, где он есть) справляется.
    assert SecBox(new_key).open(sealed) == "secret-2"


def test_multi_key_without_version_labels():
    """CSV без меток версий (просто список ключей) тоже работает."""
    old_key = SecBox.new_key()
    new_key = SecBox.new_key()
    sealed = SecBox(old_key).seal("secret-3")

    box = SecBox(f"{new_key},{old_key}")
    assert box.open(sealed) == "secret-3"


def test_multi_key_dropping_old_key_breaks_old_ciphertext():
    """После удаления старого ключа из списка старые данные больше не читаются."""
    old_key = SecBox.new_key()
    new_key = SecBox.new_key()
    sealed = SecBox(old_key).seal("secret-4")

    box_without_old = SecBox(new_key)
    with pytest.raises(RuntimeError):
        box_without_old.open(sealed)
