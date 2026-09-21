"""HashiCorp Vault как хранилище секретов (KV v2 поверх httpx)."""

from __future__ import annotations

import httpx

from .base import SecretStore


class VaultSecretStore(SecretStore):
    """Секреты в HashiCorp Vault (движок KV версии 2)."""

    name = "vault"

    def __init__(
        self,
        addr: str,
        token: str | None,
        mount: str,
        prefix: str,
        *,
        auth: str = "token",
        role_id: str | None = None,
        secret_id: str | None = None,
        auth_mount: str = "approle",
        tls_verify: bool = True,
        ca_file: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        """:arg addr: адрес Vault; :arg token: bootstrap-токен для token auth;
        :arg mount: KV-маунт; :arg prefix: префикс пути секрета.

        AppRole credentials используются только для получения короткоживущего
        токена через Vault API и не отправляются в KV-запросах.
        """
        self.addr = addr.rstrip("/")
        self.mount = mount.strip("/")
        self.prefix = prefix.strip("/")
        self._client = client or httpx.Client(
            verify=ca_file or tls_verify,
            timeout=httpx.Timeout(10.0),
        )
        self._owns_client = client is None
        self._headers = {"X-Vault-Token": token} if token else {}
        if auth == "approle":
            if not (role_id and secret_id):
                raise ValueError("vault: AppRole requires role_id and secret_id")
            response = self._client.post(
                f"{self.addr}/v1/auth/{auth_mount.strip('/')}/login",
                json={"role_id": role_id, "secret_id": secret_id},
            )
            response.raise_for_status()
            token = response.json().get("auth", {}).get("client_token")
            if not token:
                raise RuntimeError("vault: AppRole login returned no client token")
            self._headers = {"X-Vault-Token": token}
        elif auth != "token":
            raise ValueError("vault: auth must be token or approle")

    def _url(self, key: str) -> str:
        path = "/".join(part for part in (self.prefix, key.strip("/")) if part)
        return f"{self.addr}/v1/{self.mount}/data/{path}"

    def get(self, key: str) -> str | None:
        resp = self._client.get(self._url(key), headers=self._headers)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data", {}).get("data")
        if not isinstance(data, dict):
            raise RuntimeError("vault: invalid KV v2 response")
        value = data.get("value")
        if value is not None and not isinstance(value, str):
            raise RuntimeError("vault: secret value must be a string")
        return value or None

    def put(self, key: str, value: str) -> None:
        resp = self._client.post(
            self._url(key),
            headers=self._headers,
            json={"data": {"value": value}},
        )
        resp.raise_for_status()

    def close(self) -> None:
        """Закрыть HTTP-клиент, созданный этим store."""
        if self._owns_client:
            self._client.close()


__all__ = ["VaultSecretStore"]
