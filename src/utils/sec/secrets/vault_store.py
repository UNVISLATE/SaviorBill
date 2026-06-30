"""HashiCorp Vault как хранилище секретов (KV v2 поверх httpx)."""

from __future__ import annotations

import httpx

from .base import SecretStore


class VaultSecretStore(SecretStore):
    """Секреты в HashiCorp Vault (движок KV версии 2)."""

    name = "vault"

    def __init__(self, addr: str, token: str, mount: str, prefix: str) -> None:
        """:arg addr: адрес Vault; :arg token: токен; :arg mount: KV-маунт;
        :arg prefix: префикс пути секрета."""
        self.addr = addr.rstrip("/")
        self.mount = mount.strip("/")
        self.prefix = prefix
        self._headers = {"X-Vault-Token": token}

    def _url(self, key: str) -> str:
        return f"{self.addr}/v1/{self.mount}/data/{self.prefix}{key}"

    def get(self, key: str) -> str | None:
        resp = httpx.get(self._url(key), headers=self._headers, timeout=10.0)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json().get("data", {}).get("data", {})
        value = data.get("value")
        return value or None

    def put(self, key: str, value: str) -> None:
        resp = httpx.post(
            self._url(key),
            headers=self._headers,
            json={"data": {"value": value}},
            timeout=10.0,
        )
        resp.raise_for_status()


__all__ = ["VaultSecretStore"]
