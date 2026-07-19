"""Хранилище файлов mediaworker: локальная ФС и S3.

Только операции с файлами: сохранение оригинала (стрим), запись итогового файла,
удаление, presigned-URL для S3. Postgres здесь нет.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncIterator

from utils.config import Config


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
        доверие клиентскому вводу (см. AUDIT.md M1).
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

    async def put_final(self, key: str, src_path: str, mime: str) -> None:
        """Разместить итоговый файл в хранилище (fs — переместить, s3 — залить)."""
        if self.cfg.backend == "s3":
            await self._s3_upload(key, src_path, mime)
            self._safe_unlink(src_path)
        else:
            dst = self.media_fs_path(key)
            os.replace(src_path, dst)

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
                    pass

    @staticmethod
    def _safe_unlink(path: str) -> None:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


__all__ = ["Storage"]
