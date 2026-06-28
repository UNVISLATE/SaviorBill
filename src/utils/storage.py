"""Хранилище загружаемых файлов: локальная ФС или S3-совместимое хранилище.

Используется для медиа товаров, иконок каталогов, аватарок пользователей. Бэкенд
выбирается в конфиге (``STORAGE_BACKEND``). По умолчанию — локальная ФС в
``DATA_DIR/uploads``. S3 подключается опционально (``aioboto3`` загружается лениво).
"""

from __future__ import annotations

import uuid
from pathlib import PurePosixPath

from utils.config import AppConfig


class StorageSvc:
    """Абстракция над файловым хранилищем (fs | s3)."""

    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.backend = cfg.STORAGE_BACKEND

    @staticmethod
    def _key(folder: str, filename: str) -> str:
        """Сгенерировать уникальный ключ объекта вида ``folder/uuid.ext``."""
        suffix = PurePosixPath(filename).suffix
        return f"{folder.strip('/')}/{uuid.uuid4().hex}{suffix}"

    async def save(
        self, folder: str, filename: str, data: bytes, content_type: str | None = None
    ) -> str:
        """Сохранить файл и вернуть его публичный URL/относительный путь."""
        key = self._key(folder, filename)
        if self.backend == "s3":
            return await self._save_s3(key, data, content_type)
        return self._save_fs(key, data)

    async def delete(self, key: str) -> None:
        """Удалить файл по ключу (best-effort)."""
        if self.backend == "s3":
            await self._delete_s3(key)
        else:
            self._delete_fs(key)

    # --- локальная ФС -----------------------------------------------------
    def _save_fs(self, key: str, data: bytes) -> str:
        target = self.cfg.uploads_dir / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return f"/uploads/{key}"

    def _delete_fs(self, key: str) -> None:
        target = self.cfg.uploads_dir / key.removeprefix("/uploads/").lstrip("/")
        if target.exists():
            target.unlink()

    # --- S3 ---------------------------------------------------------------
    def _s3_session(self):
        import aioboto3  # ленивый импорт: ставится только при использовании S3

        return aioboto3.Session()

    async def _save_s3(self, key: str, data: bytes, content_type: str | None) -> str:
        session = self._s3_session()
        async with session.client(
            "s3",
            endpoint_url=self.cfg.S3_ENDPOINT,
            region_name=self.cfg.S3_REGION,
            aws_access_key_id=self.cfg.S3_KEY,
            aws_secret_access_key=self.cfg.S3_SECRET,
        ) as s3:
            extra = {"ContentType": content_type} if content_type else {}
            await s3.put_object(Bucket=self.cfg.S3_BUCKET, Key=key, Body=data, **extra)
        base = (self.cfg.S3_PUBLIC_URL or "").rstrip("/")
        return f"{base}/{key}" if base else key

    async def _delete_s3(self, key: str) -> None:
        session = self._s3_session()
        async with session.client(
            "s3",
            endpoint_url=self.cfg.S3_ENDPOINT,
            region_name=self.cfg.S3_REGION,
            aws_access_key_id=self.cfg.S3_KEY,
            aws_secret_access_key=self.cfg.S3_SECRET,
        ) as s3:
            await s3.delete_object(Bucket=self.cfg.S3_BUCKET, Key=key)


__all__ = ["StorageSvc"]
