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
    from utils.config import AppConfig

# Поддерживаемые бэкенды (значения ENV SECRETS_BACKEND).
BACKENDS = ("file", "aws", "gcp", "azure", "vault")


def _file_paths(cfg: "AppConfig") -> dict[str, Path]:
    """Карта «имя секрета → путь файла» для файлового бэкенда.

    :arg cfg: конфигурация приложения.
    :return: отображение логических имён на пути.
    """
    paths: dict[str, Path] = {
        SecretName.SECRETS_KEY: cfg.secret_key_file,
        SecretName.JWT: Path(cfg.JWT_SECRET_FILE),
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
        if not (cfg.SECRETS_VAULT_ADDR and cfg.SECRETS_VAULT_TOKEN):
            raise ValueError(
                "vault: SECRETS_VAULT_ADDR and SECRETS_VAULT_TOKEN are needed"
            )
        from .vault_store import VaultSecretStore

        return VaultSecretStore(
            cfg.SECRETS_VAULT_ADDR,
            cfg.SECRETS_VAULT_TOKEN,
            cfg.SECRETS_VAULT_MOUNT,
            cfg.SECRETS_PREFIX,
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
