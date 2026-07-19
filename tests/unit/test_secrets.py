"""Юнит-тесты хранилищ секретов и резолвера (файловый бэкенд)."""

from __future__ import annotations

from pathlib import Path

import pytest

from utils.config import AppConfig
from security.sec.secrets import (
    BACKENDS,
    FileSecretStore,
    SecretName,
    SecretResolver,
    build_secret_store,
)
from security.sec.secrets.resolve import resolve_secrets

pytestmark = pytest.mark.unit


def test_file_store_roundtrip(tmp_path: Path):
    store = FileSecretStore({SecretName.JWT: tmp_path / "jwt.key"})
    assert store.get(SecretName.JWT) is None
    store.put(SecretName.JWT, "s3cr3t")
    assert store.get(SecretName.JWT) == "s3cr3t"
    assert store.exists(SecretName.JWT) is True


def test_file_store_put_unknown_key_raises(tmp_path: Path):
    store = FileSecretStore({})
    with pytest.raises(KeyError):
        store.put("nope", "x")


def test_resolver_generates_once(tmp_path: Path):
    store = FileSecretStore({SecretName.JWT: tmp_path / "jwt.key"})
    res = SecretResolver(store)
    calls = {"n": 0}

    def gen() -> str:
        calls["n"] += 1
        return f"gen{calls['n']}"

    first = res.ensure(SecretName.JWT, gen)
    second = res.ensure(SecretName.JWT, gen)
    assert first == "gen1"
    assert second == "gen1"  # повторно не генерируется
    assert calls["n"] == 1


def test_resolver_fallback_without_generator(tmp_path: Path):
    store = FileSecretStore({})
    res = SecretResolver(store)
    assert res.ensure(SecretName.DB_PASS, fallback="envpass") == "envpass"


def test_build_store_file_default():
    cfg = AppConfig(DB_PASS="x", JWT_SECRET="y")
    store = build_secret_store(cfg)
    assert isinstance(store, FileSecretStore)
    assert store.name == "file"


def test_build_store_unknown_backend():
    cfg = AppConfig(DB_PASS="x", JWT_SECRET="y", SECRETS_BACKEND="nope")
    with pytest.raises(ValueError):
        build_secret_store(cfg)


def test_build_store_vault_requires_creds():
    cfg = AppConfig(DB_PASS="x", JWT_SECRET="y", SECRETS_BACKEND="vault")
    with pytest.raises(ValueError):
        build_secret_store(cfg)


def test_backends_catalog():
    assert set(BACKENDS) == {"file", "aws", "gcp", "azure", "vault"}


def test_resolve_secrets_generates_and_persists(tmp_path: Path, monkeypatch):
    # Очищаем прямые значения из ENV, чтобы проверить генерацию в файлы.
    for var in ("JWT_SECRET", "LUA_SERVICE_TOKEN", "SECRETS_KEY"):
        monkeypatch.delenv(var, raising=False)
    cfg = AppConfig(DB_PASS="dbpass", DATA_DIR=str(tmp_path))
    backend = resolve_secrets(cfg)
    assert backend == "file"
    # Генерируемые секреты созданы и записаны в файлы.
    assert cfg.JWT_SECRET
    assert cfg.SECRETS_KEY
    assert cfg.LUA_SERVICE_TOKEN
    assert Path(cfg.JWT_SECRET_FILE).exists()
    assert Path(cfg.SECRETS_KEY_PATH).exists()
    # Предоставляемый секрет берётся из ENV-отката.
    assert cfg.DB_PASS == "dbpass"

    # Повторный запуск читает те же значения (не пересоздаёт).
    jwt_before = cfg.JWT_SECRET
    cfg2 = AppConfig(DB_PASS="dbpass", DATA_DIR=str(tmp_path))
    resolve_secrets(cfg2)
    assert cfg2.JWT_SECRET == jwt_before


def test_resolve_secrets_requires_db_pass(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DB_PASS", raising=False)
    cfg = AppConfig(DATA_DIR=str(tmp_path))  # без DB_PASS
    with pytest.raises(RuntimeError):
        resolve_secrets(cfg)
