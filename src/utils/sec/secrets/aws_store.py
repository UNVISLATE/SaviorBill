"""AWS Secrets Manager как хранилище секретов (boto3, ленивый импорт)."""

from __future__ import annotations

from .base import SecretStore


class AWSSecretStore(SecretStore):
    """Секреты в AWS Secrets Manager."""

    name = "aws"

    def __init__(self, region: str | None, prefix: str) -> None:
        """:arg region: регион AWS; :arg prefix: префикс имени секрета."""
        import boto3  # ленивый импорт: SDK нужен только для этого бэкенда

        self.prefix = prefix
        self._cli = boto3.client("secretsmanager", region_name=region)

    def _id(self, key: str) -> str:
        return f"{self.prefix}{key}"

    def get(self, key: str) -> str | None:
        from botocore.exceptions import ClientError

        try:
            resp = self._cli.get_secret_value(SecretId=self._id(key))
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
                return None
            raise
        return resp.get("SecretString") or None

    def put(self, key: str, value: str) -> None:
        from botocore.exceptions import ClientError

        try:
            self._cli.create_secret(Name=self._id(key), SecretString=value)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ResourceExistsException":
                self._cli.put_secret_value(SecretId=self._id(key), SecretString=value)
            else:
                raise


__all__ = ["AWSSecretStore"]
