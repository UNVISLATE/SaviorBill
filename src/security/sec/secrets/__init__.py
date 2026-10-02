"""Хранилища секретов: файлы (по умолчанию) и облачные менеджеры.

Бэкенд выбирается через ENV ``SECRETS_BACKEND`` (file/aws/gcp/azure/vault).
Политика: секрет создаётся в хранилище только если его там нет, далее всегда
читается оттуда.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .base import SecretName, SecretResolver, SecretStore
from .file_store import FileSecretStore

if TYPE_CHECKING:  # избегаем циклического импорта на рантайме
    from core.config import AppConfig

# Поддерживаемые бэкенды (значения ENV SECRETS_BACKEND).
BACKENDS = ("file", "aws", "gcp", "azure", "vault")


def _file_paths(cfg: "AppConfig") -> dict[str, Path]:
    """Карта «имя секрета → путь файла» для файлового бэкенда.

    :arg cfg: конфигурация приложения.
    :return: отображение логических имён на пути.
    """
    paths: dict[str, Path] = {
        SecretName.SECRETS_KEY: cfg.secret_key_file,
        SecretName.AUTH_SESSION_HASH_KEY: Path(cfg.AUTH_SESSION_HASH_KEY_FILE),
        SecretName.JWT_PRIVATE: Path(cfg.JWT_PRIVATE_KEY_FILE),
        SecretName.JWT_PUBLIC: Path(cfg.JWT_PUBLIC_KEY_FILE),
        SecretName.JWT_KID: Path(cfg.JWT_KID_FILE),
        SecretName.JWT_PUBLIC_PREV: Path(cfg.JWT_PUBLIC_KEY_PREV_FILE),
        SecretName.JWT_KID_PREV: Path(cfg.JWT_KID_PREV_FILE),
        SecretName.LUA_TOKEN: Path(cfg.LUA_SERVICE_TOKEN_FILE),
    }
    # Предоставляемые (негенерируемые) секреты — только если задан путь файла.
    if cfg.DB_PASS_FILE:
        paths[SecretName.DB_PASS] = Path(cfg.DB_PASS_FILE)
    if cfg.SMTP_PASS_FILE:
        paths[SecretName.SMTP_PASS] = Path(cfg.SMTP_PASS_FILE)
    if cfg.S3_SECRET_FILE:
        paths[SecretName.S3_SECRET] = Path(cfg.S3_SECRET_FILE)
    return paths


def build_secret_store(cfg: "AppConfig") -> SecretStore:
    """Собрать хранилище секретов по ``cfg.SECRETS_BACKEND``.

    :arg cfg: конфигурация приложения.
    :return: реализация ``SecretStore``.
    :raises ValueError: при неизвестном бэкенде или нехватке параметров.
    """
    backend = (cfg.SECRETS_BACKEND or "file").lower()

    if backend == "file":
        return FileSecretStore(_file_paths(cfg))

    if backend == "vault":
        if not cfg.SECRETS_VAULT_ADDR:
            raise ValueError("vault: SECRETS_VAULT_ADDR is needed")
        auth = (cfg.SECRETS_VAULT_AUTH or "token").lower()
        if auth not in {"token", "approle"}:
            raise ValueError("vault: SECRETS_VAULT_AUTH must be token or approle")
        if auth == "token" and not cfg.SECRETS_VAULT_TOKEN:
            raise ValueError("vault: SECRETS_VAULT_TOKEN is needed for token auth")
        if auth == "approle" and not (
            cfg.SECRETS_VAULT_ROLE_ID and cfg.SECRETS_VAULT_SECRET_ID
        ):
            raise ValueError(
                "vault: SECRETS_VAULT_ROLE_ID and SECRETS_VAULT_SECRET_ID "
                "are needed for approle auth"
            )
        from .vault_store import VaultSecretStore

        return VaultSecretStore(
            cfg.SECRETS_VAULT_ADDR,
            cfg.SECRETS_VAULT_TOKEN,
            cfg.SECRETS_VAULT_MOUNT,
            cfg.SECRETS_PREFIX,
            auth=auth,
            role_id=cfg.SECRETS_VAULT_ROLE_ID,
            secret_id=cfg.SECRETS_VAULT_SECRET_ID,
            auth_mount=cfg.SECRETS_VAULT_AUTH_MOUNT,
            tls_verify=cfg.SECRETS_VAULT_TLS_VERIFY,
            ca_file=cfg.SECRETS_VAULT_CA_FILE,
        )

    if backend == "aws":
        from .aws_store import AWSSecretStore

        return AWSSecretStore(cfg.SECRETS_AWS_REGION, cfg.SECRETS_PREFIX)

    if backend == "gcp":
        if not cfg.SECRETS_GCP_PROJECT:
            raise ValueError("gcp: need SECRETS_GCP_PROJECT")
        from .gcp_store import GCPSecretStore

        return GCPSecretStore(cfg.SECRETS_GCP_PROJECT, cfg.SECRETS_PREFIX)

    if backend == "azure":
        if not cfg.SECRETS_AZURE_VAULT_URL:
            raise ValueError("azure: need SECRETS_AZURE_VAULT_URL")
        from .azure_store import AzureSecretStore

        return AzureSecretStore(cfg.SECRETS_AZURE_VAULT_URL, cfg.SECRETS_PREFIX)

    raise ValueError(f"unknown SECRETS_BACKEND: {backend!r} (from {BACKENDS})")


__all__ = [
    "SecretName",
    "SecretStore",
    "SecretResolver",
    "FileSecretStore",
    "BACKENDS",
    "build_secret_store",
]
