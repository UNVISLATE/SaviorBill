"""Google Secret Manager как хранилище секретов (ленивый импорт SDK)."""

from __future__ import annotations

from .base import SecretStore


def _safe(name: str) -> str:
    """Привести имя к допустимому в Secret Manager (``[A-Za-z0-9_-]``)."""
    return "".join(c if (c.isalnum() or c in "-_") else "-" for c in name)


class GCPSecretStore(SecretStore):
    """Секреты в Google Secret Manager."""

    name = "gcp"

    def __init__(self, project: str, prefix: str) -> None:
        """:arg project: id проекта GCP; :arg prefix: префикс имени секрета."""
        from google.cloud import secretmanager  # ленивый импорт

        self.project = project
        self.prefix = prefix
        self._cli = secretmanager.SecretManagerServiceClient()
        self._sm = secretmanager

    def _sid(self, key: str) -> str:
        return _safe(f"{self.prefix}{key}")

    def get(self, key: str) -> str | None:
        from google.api_core.exceptions import NotFound

        name = f"projects/{self.project}/secrets/{self._sid(key)}/versions/latest"
        try:
            resp = self._cli.access_secret_version(name=name)
        except NotFound:
            return None
        return resp.payload.data.decode("utf-8") or None

    def put(self, key: str, value: str) -> None:
        from google.api_core.exceptions import AlreadyExists

        parent = f"projects/{self.project}"
        sid = self._sid(key)
        try:
            self._cli.create_secret(
                parent=parent,
                secret_id=sid,
                secret={"replication": {"automatic": {}}},
            )
        except AlreadyExists:
            pass
        self._cli.add_secret_version(
            parent=f"{parent}/secrets/{sid}",
            payload={"data": value.encode("utf-8")},
        )


__all__ = ["GCPSecretStore"]
