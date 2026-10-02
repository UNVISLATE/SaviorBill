"""Юнит-тесты хранилищ секретов и резолвера (файловый бэкенд)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core.config import AppConfig
from security.sec.secrets import (
    BACKENDS,
    FileSecretStore,
    SecretName,
    SecretResolver,
    build_secret_store,
)
from security.sec.secrets.resolve import resolve_secrets, rotate_jwt_keypair

pytestmark = pytest.mark.unit


def test_file_store_roundtrip(tmp_path: Path):
    store = FileSecretStore({SecretName.JWT_PRIVATE: tmp_path / "jwt_private.pem"})
    assert store.get(SecretName.JWT_PRIVATE) is None
    store.put(SecretName.JWT_PRIVATE, "s3cr3t")
    assert store.get(SecretName.JWT_PRIVATE) == "s3cr3t"
    assert store.exists(SecretName.JWT_PRIVATE) is True


def test_file_store_put_unknown_key_raises(tmp_path: Path):
    store = FileSecretStore({})
    with pytest.raises(KeyError):
        store.put("nope", "x")


def test_resolver_generates_once(tmp_path: Path):
    store = FileSecretStore({SecretName.JWT_PRIVATE: tmp_path / "jwt_private.pem"})
    res = SecretResolver(store)
    calls = {"n": 0}

    def gen() -> str:
        calls["n"] += 1
        return f"gen{calls['n']}"

    first = res.ensure(SecretName.JWT_PRIVATE, gen)
    second = res.ensure(SecretName.JWT_PRIVATE, gen)
    assert first == "gen1"
    assert second == "gen1"  # повторно не генерируется
    assert calls["n"] == 1


def test_resolver_fallback_without_generator(tmp_path: Path):
    store = FileSecretStore({})
    res = SecretResolver(store)
    assert res.ensure(SecretName.DB_PASS, fallback="envpass") == "envpass"


def test_build_store_file_default():
    cfg = AppConfig(DB_PASS="x")
    store = build_secret_store(cfg)
    assert isinstance(store, FileSecretStore)
    assert store.name == "file"


def test_build_store_unknown_backend():
    cfg = AppConfig(DB_PASS="x", SECRETS_BACKEND="nope")
    with pytest.raises(ValueError):
        build_secret_store(cfg)


def test_build_store_vault_requires_creds():
    cfg = AppConfig(DB_PASS="x", SECRETS_BACKEND="vault")
    with pytest.raises(ValueError):
        build_secret_store(cfg)


def test_backends_catalog():
    assert set(BACKENDS) == {"file", "aws", "gcp", "azure", "vault"}


def test_resolve_secrets_generates_and_persists(tmp_path: Path, monkeypatch):
    # Очищаем прямые значения из ENV, чтобы проверить генерацию в файлы.
    for var in (
        "JWT_PRIVATE_KEY",
        "JWT_PUBLIC_KEY",
        "JWT_KID",
        "LUA_SERVICE_TOKEN",
        "SECRETS_KEY",
        "AUTH_SESSION_HASH_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    cfg = AppConfig(
        DEBUG=True,
        DB_PASS="dbpass",
        DATA_DIR=str(tmp_path / "data"),
        PRIVATE_DATA_DIR=str(tmp_path / "private"),
    )
    backend = resolve_secrets(cfg)
    assert backend == "file"
    # Генерируемые секреты созданы и записаны в файлы.
    assert cfg.JWT_PRIVATE_KEY
    assert cfg.JWT_PUBLIC_KEY
    assert cfg.JWT_KID
    assert cfg.SECRETS_KEY
    assert cfg.AUTH_SESSION_HASH_KEY
    assert cfg.LUA_SERVICE_TOKEN
    assert Path(cfg.JWT_PRIVATE_KEY_FILE).exists()
    assert Path(cfg.JWT_PUBLIC_KEY_FILE).exists()
    assert Path(cfg.JWT_KID_FILE).exists()
    assert Path(cfg.SECRETS_KEY_PATH).exists()
    # Предоставляемый секрет берётся из ENV-отката.
    assert cfg.DB_PASS == "dbpass"

    # Повторный запуск читает те же значения (не пересоздаёт).
    private_before = cfg.JWT_PRIVATE_KEY
    public_before = cfg.JWT_PUBLIC_KEY
    kid_before = cfg.JWT_KID
    cfg2 = AppConfig(
        DEBUG=True,
        DB_PASS="dbpass",
        DATA_DIR=str(tmp_path / "data"),
        PRIVATE_DATA_DIR=str(tmp_path / "private"),
    )
    resolve_secrets(cfg2)
    # Файловое хранилище нормализует хвостовые пробелы при чтении — сравниваем
    # содержательную часть PEM, а не байт-в-байт.
    assert cfg2.JWT_PRIVATE_KEY.strip() == private_before.strip()
    assert cfg2.JWT_PUBLIC_KEY.strip() == public_before.strip()
    assert cfg2.JWT_KID == kid_before


def test_rotate_jwt_keypair_preserves_previous_for_grace_period(tmp_path: Path, monkeypatch):
    for var in ("JWT_PRIVATE_KEY", "JWT_PUBLIC_KEY", "JWT_KID"):
        monkeypatch.delenv(var, raising=False)
    cfg = AppConfig(
        DEBUG=True,
        DB_PASS="dbpass",
        DATA_DIR=str(tmp_path / "data"),
        PRIVATE_DATA_DIR=str(tmp_path / "private"),
    )
    resolve_secrets(cfg)
    old_public, old_kid = cfg.JWT_PUBLIC_KEY, cfg.JWT_KID

    new_kid = rotate_jwt_keypair(cfg)

    assert new_kid != old_kid
    assert cfg.JWT_KID == new_kid
    assert cfg.JWT_PUBLIC_KEY != old_public
    # Старый ключ остаётся доступным для верификации (grace-период).
    assert cfg.JWT_KID_PREV == old_kid
    assert cfg.JWT_PUBLIC_KEY_PREV == old_public
    keys = cfg.jwt_public_keys()
    assert set(keys) == {new_kid, old_kid}
    assert keys[old_kid] == old_public
    assert keys[new_kid] == cfg.JWT_PUBLIC_KEY


def test_rotate_jwt_keypair_requires_existing_keys(tmp_path: Path, monkeypatch):
    for var in ("JWT_PRIVATE_KEY", "JWT_PUBLIC_KEY", "JWT_KID"):
        monkeypatch.delenv(var, raising=False)
    cfg = AppConfig(DB_PASS="dbpass", DATA_DIR=str(tmp_path))
    with pytest.raises(RuntimeError):
        rotate_jwt_keypair(cfg)


def test_resolve_secrets_requires_db_pass(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DB_PASS", raising=False)
    cfg = AppConfig(DATA_DIR=str(tmp_path))  # без DB_PASS
    with pytest.raises(RuntimeError):
        resolve_secrets(cfg)


def test_aws_store_roundtrip(monkeypatch):
    import boto3
    from security.sec.secrets.aws_store import AWSSecretStore

    values: dict[str, str] = {}

    class Client:
        def get_secret_value(self, *, SecretId):
            if SecretId not in values:
                from botocore.exceptions import ClientError

                raise ClientError(
                    {"Error": {"Code": "ResourceNotFoundException"}},
                    "GetSecretValue",
                )
            return {"SecretString": values[SecretId]}

        def create_secret(self, *, Name, SecretString):
            from botocore.exceptions import ClientError

            if Name in values:
                raise ClientError(
                    {"Error": {"Code": "ResourceExistsException"}},
                    "CreateSecret",
                )
            values[Name] = SecretString

        def put_secret_value(self, *, SecretId, SecretString):
            values[SecretId] = SecretString

    monkeypatch.setattr(boto3, "client", lambda *_args, **_kwargs: Client())
    store = AWSSecretStore("eu-test-1", "saviorbill/")
    assert store.get(SecretName.DB_PASS) is None
    store.put(SecretName.DB_PASS, "first")
    store.put(SecretName.DB_PASS, "second")
    assert store.get(SecretName.DB_PASS) == "second"


def test_gcp_store_roundtrip(monkeypatch):
    from google.api_core.exceptions import NotFound
    from google.cloud import secretmanager
    from security.sec.secrets.gcp_store import GCPSecretStore

    values: dict[str, str] = {}

    class Client:
        def access_secret_version(self, *, name):
            if name not in values:
                raise NotFound("missing")
            return SimpleNamespace(payload=SimpleNamespace(data=values[name].encode()))

        def create_secret(self, *, parent, secret_id, secret):
            values.setdefault(f"{parent}/secrets/{secret_id}/versions/latest", "")

        def add_secret_version(self, *, parent, payload):
            values[f"{parent}/versions/latest"] = payload["data"].decode()

    monkeypatch.setattr(secretmanager, "SecretManagerServiceClient", Client)
    store = GCPSecretStore("project", "saviorbill/")
    store.put(SecretName.DB_PASS, "dbpass")
    assert store.get(SecretName.DB_PASS) == "dbpass"


def test_azure_store_roundtrip(monkeypatch):
    from azure.identity import DefaultAzureCredential
    from azure.keyvault import secrets
    from security.sec.secrets.azure_store import AzureSecretStore

    values: dict[str, str] = {}

    class Client:
        def __init__(self, *, vault_url, credential):
            assert vault_url == "https://vault.vault.azure.net/"
            assert isinstance(credential, DefaultAzureCredential)

        def get_secret(self, name):
            if name not in values:
                from azure.core.exceptions import ResourceNotFoundError

                raise ResourceNotFoundError("missing")
            return SimpleNamespace(value=values[name])

        def set_secret(self, name, value):
            values[name] = value

    monkeypatch.setattr(secrets, "SecretClient", Client)
    store = AzureSecretStore("https://vault.vault.azure.net/", "saviorbill/")
    store.put(SecretName.DB_PASS, "dbpass")
    assert store.get(SecretName.DB_PASS) == "dbpass"


def test_vault_store_token_roundtrip():
    import httpx
    from security.sec.secrets.vault_store import VaultSecretStore

    responses = {
        ("GET", "https://vault/v1/secret/data/saviorbill/db_pass"): httpx.Response(
            404
        ),
        ("POST", "https://vault/v1/secret/data/saviorbill/db_pass"): httpx.Response(
            204
        ),
    }

    def handler(request):
        response = responses[(request.method, str(request.url))]
        if request.method == "GET" and response.status_code == 404:
            responses[("GET", str(request.url))] = httpx.Response(
                200,
                json={"data": {"data": {"value": "dbpass"}}},
            )
        return response

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = VaultSecretStore("https://vault/", "token", "secret", "saviorbill", client=client)
    assert store.get(SecretName.DB_PASS) is None
    store.put(SecretName.DB_PASS, "dbpass")
    assert store.get(SecretName.DB_PASS) == "dbpass"
    client.close()


def test_vault_store_approle_auth():
    import httpx
    from security.sec.secrets.vault_store import VaultSecretStore

    def handler(request):
        if request.url.path == "/v1/auth/approle/login":
            return httpx.Response(200, json={"auth": {"client_token": "short-token"}})
        return httpx.Response(200, json={"data": {"data": {"value": "secret"}}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = VaultSecretStore(
        "https://vault",
        None,
        "secret",
        "saviorbill",
        auth="approle",
        role_id="role",
        secret_id="secret-id",
        client=client,
    )
    assert store.get(SecretName.DB_PASS) == "secret"
    client.close()
