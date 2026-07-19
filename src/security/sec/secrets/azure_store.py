"""Azure Key Vault как хранилище секретов (ленивый импорт SDK)."""

from __future__ import annotations

from .base import SecretStore


def _safe(name: str) -> str:
    """Привести имя к допустимому в Key Vault (``[0-9a-zA-Z-]``)."""
    return "".join(c if (c.isalnum() or c == "-") else "-" for c in name)


class AzureSecretStore(SecretStore):
    """Секреты в Azure Key Vault."""

    name = "azure"

    def __init__(self, vault_url: str, prefix: str) -> None:
        """:arg vault_url: URL хранилища Key Vault; :arg prefix: префикс имени."""
        from azure.identity import DefaultAzureCredential  # ленивый импорт
        from azure.keyvault.secrets import SecretClient

        self.prefix = prefix
        self._cli = SecretClient(
            vault_url=vault_url, credential=DefaultAzureCredential()
        )

    def _name(self, key: str) -> str:
        return _safe(f"{self.prefix}{key}")

    def get(self, key: str) -> str | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            secret = self._cli.get_secret(self._name(key))
        except ResourceNotFoundError:
            return None
        return secret.value or None

    def put(self, key: str, value: str) -> None:
        self._cli.set_secret(self._name(key), value)


__all__ = ["AzureSecretStore"]
