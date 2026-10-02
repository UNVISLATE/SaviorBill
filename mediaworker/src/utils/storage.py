"""Хранилище файлов mediaworker: локальная ФС и S3.

Только операции с файлами: сохранение оригинала (стрим), запись итогового файла,
удаление, presigned-URL для S3. Postgres здесь нет.
"""

from __future__ import annotations

import logging
import hashlib
import mimetypes
import os
import asyncio
from pathlib import Path
from typing import AsyncIterator

from botocore.exceptions import ClientError

from utils.config import Config

log = logging.getLogger("saviormedia.storage")


class Storage:
    """Абстракция над ФС/S3 для mediaworker."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        os.makedirs(cfg.uploads_dir, exist_ok=True)
        os.makedirs(cfg.media_dir, exist_ok=True)

    def _safe_fs_path(self, base_dir: str, key: str) -> str:
        """Разрешить ``key`` внутри ``base_dir``, отклонив выход за его пределы.

        В нормальном потоке ``key``/``token`` всегда server-generated (см.
        ``convert.py::target_key``, ``upload.py`` — ``uuid4().hex``), но эта
        проверка — защита в глубину на случай бага/будущего изменения, а не
        доверие клиентскому вводу.
        """
        base = Path(base_dir).resolve()
        target = (base / key).resolve()
        try:
            target.relative_to(base)
        except ValueError as exc:
            raise ValueError(f"unsafe storage key: {key!r}") from exc
        return str(target)

    # ---- оригинал (всегда локально, до конвертации) ----

    def orig_path(self, token: str) -> str:
        """Путь к оригиналу загрузки."""
        return self._safe_fs_path(self.cfg.uploads_dir, f"{token}.orig")

    async def save_stream(
        self, token: str, chunks: AsyncIterator[bytes], max_bytes: int
    ) -> int:
        """Потоково сохранить оригинал, контролируя лимит объёма.

        :arg token: идентификатор медиа.
        :arg chunks: асинхронный итератор кусков тела запроса.
        :arg max_bytes: максимально допустимый объём.
        :return: фактический размер в байтах.
        :raises ValueError: если объём превысил ``max_bytes`` (фейковый заголовок).
        """
        path = self.orig_path(token)
        total = 0
        with open(path, "wb") as f:
            async for chunk in chunks:
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    f.close()
                    self._safe_unlink(path)
                    raise ValueError("upload exceeds allowed size")
                f.write(chunk)
        return total

    # ---- итоговый файл ----

    def media_fs_path(self, key: str) -> str:
        """Путь к итоговому файлу в локальном media-каталоге."""
        return self._safe_fs_path(self.cfg.media_dir, key)

    async def inspect(self, key: str, *, expected_size: int | None = None,
                      expected_hash: str | None = None,
                      expected_mime: str | None = None) -> dict:
        """Inspect one final object without silently treating storage errors as missing."""
        if self.cfg.backend == "s3":
            try:
                session = self._s3_session()
                async with session.client(
                    "s3",
                    endpoint_url=self.cfg.s3_endpoint,
                    region_name=self.cfg.s3_region,
                    aws_access_key_id=self.cfg.s3_key,
                    aws_secret_access_key=self.cfg.s3_secret,
                ) as client:
                    head = await client.head_object(
                        Bucket=self.cfg.s3_bucket, Key=key
                    )
            except ClientError as exc:
                response = getattr(exc, "response", {}) or {}
                code = str(response.get("Error", {}).get("Code", ""))
                if code in {"404", "NoSuchKey", "NotFound"}:
                    return {"status": "missing", "key": key}
                return {"status": "storage_unavailable", "key": key}
            except OSError:
                return {"status": "storage_unavailable", "key": key}
            size = head.get("ContentLength")
            mime = head.get("ContentType")
            if expected_size is not None and size != expected_size:
                return {"status": "corrupt", "key": key, "size": size, "mime": mime}
            if expected_mime and mime and mime != expected_mime:
                return {"status": "corrupt", "key": key, "size": size, "mime": mime}
            return {"status": "ready", "key": key, "size": size, "mime": mime}

        try:
            path = self.media_fs_path(key)
            stat = await asyncio.to_thread(os.stat, path)
        except FileNotFoundError:
            return {"status": "missing", "key": key}
        except (OSError, ValueError):
            return {"status": "storage_unavailable", "key": key}
        mime, _ = mimetypes.guess_type(path)
        if expected_size is not None and stat.st_size != expected_size:
            return {"status": "corrupt", "key": key, "size": stat.st_size, "mime": mime}
        if expected_mime and mime and mime != expected_mime:
            return {"status": "corrupt", "key": key, "size": stat.st_size, "mime": mime}
        if expected_hash:
            try:
                digest = await asyncio.to_thread(self._sha256_path, path)
            except OSError:
                return {"status": "storage_unavailable", "key": key}
            if digest != expected_hash:
                return {
                    "status": "corrupt",
                    "key": key,
                    "size": stat.st_size,
                    "mime": mime,
                }
        return {"status": "ready", "key": key, "size": stat.st_size, "mime": mime}

    @staticmethod
    def _sha256_path(path: str) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    async def put_final(self, key: str, src_path: str, mime: str) -> None:
        """Разместить итоговый файл в хранилище (fs — переместить, s3 — залить)."""
        if self.cfg.backend == "s3":
            await self._s3_upload(key, src_path, mime)
            self._safe_unlink(src_path)
        else:
            dst = self.media_fs_path(key)
            os.replace(src_path, dst)

    async def link_or_copy(self, key: str, src_path: str, existing_key: str) -> bool:
        """Дедуп по содержимому (fs-only): хардлинк вместо копирования новых байт.

        Вызывающий (``worker.py::_publish``) уже проверил, что физический
        файл ``existing_key`` содержит побайтово идентичные данные (тот же
        sha256, см. ``Worker._convert``). Хардлинк — сам по себе
        reference-counted на уровне ФС: удаление одного из имён (``key`` или
        ``existing_key``) не трогает данные, пока жива хотя бы одна ссылка
        (см. ``delete()``) — отдельный счётчик в БД не нужен.

        S3 хардлинков не имеет — там просто ``return False`` (вызывающий
        сохранит обычным ``put_final``, без экономии места; полноценный s3
        дедуп через CopyObject — за рамками этой реализации).

        :return: ``True`` при успехе (``src_path`` уже удалён), ``False`` —
            нужно вызвать ``put_final`` как обычно (иная ФС/файл исчез).
        """
        if self.cfg.backend == "s3":
            return False
        dst = self.media_fs_path(key)
        existing = self.media_fs_path(existing_key)
        try:
            os.link(existing, dst)
        except OSError:
            return False
        self._safe_unlink(src_path)
        return True

    async def delete(self, paths: list[str]) -> None:
        """Удалить файлы из хранилища (best-effort)."""
        if self.cfg.backend == "s3":
            await self._s3_delete(paths)
        else:
            for key in paths:
                self._safe_unlink(self.media_fs_path(key))

    async def presign(self, key: str, expires: int = 3600) -> str | None:
        """Сгенерировать временную ссылку S3 (для отдачи файла)."""
        if self.cfg.backend != "s3":
            return None
        session = self._s3_session()
        async with session.client(
            "s3",
            endpoint_url=self.cfg.s3_endpoint,
            region_name=self.cfg.s3_region,
            aws_access_key_id=self.cfg.s3_key,
            aws_secret_access_key=self.cfg.s3_secret,
        ) as client:
            return await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.cfg.s3_bucket, "Key": key},
                ExpiresIn=expires,
            )

    # ---- S3 helpers ----

    def _s3_session(self):
        import aioboto3

        return aioboto3.Session()

    async def _s3_upload(self, key: str, src_path: str, mime: str) -> None:
        session = self._s3_session()
        async with session.client(
            "s3",
            endpoint_url=self.cfg.s3_endpoint,
            region_name=self.cfg.s3_region,
            aws_access_key_id=self.cfg.s3_key,
            aws_secret_access_key=self.cfg.s3_secret,
        ) as client:
            with open(src_path, "rb") as f:
                await client.put_object(
                    Bucket=self.cfg.s3_bucket,
                    Key=key,
                    Body=f,
                    ContentType=mime,
                )

    async def _s3_delete(self, keys: list[str]) -> None:
        session = self._s3_session()
        async with session.client(
            "s3",
            endpoint_url=self.cfg.s3_endpoint,
            region_name=self.cfg.s3_region,
            aws_access_key_id=self.cfg.s3_key,
            aws_secret_access_key=self.cfg.s3_secret,
        ) as client:
            for key in keys:
                try:
                    await client.delete_object(Bucket=self.cfg.s3_bucket, Key=key)
                except Exception:  # noqa: BLE001 — best-effort
                    log.warning("s3: failed to delete key=%s", key, exc_info=True)

    @staticmethod
    def _safe_unlink(path: str) -> None:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


__all__ = ["Storage"]
