"""Конвертация медиа через ffmpeg: изображения -> webp, видео -> webm."""

from __future__ import annotations

import asyncio
import os

from config import Config

_IMAGE_KINDS = {"image", "icon", "avatar"}
_VIDEO_KINDS = {"video"}


class ConvertError(RuntimeError):
    """Ошибка конвертации ffmpeg."""


def target_key(token: str, kind: str) -> tuple[str, str]:
    """Ключ итогового файла и его MIME по виду медиа."""
    if kind in _VIDEO_KINDS:
        return f"{token}.webm", "video/webm"
    return f"{token}.webp", "image/webp"


async def convert(cfg: Config, kind: str, src: str, dst: str) -> None:
    """Сконвертировать ``src`` в ``dst`` (webp/webm) через ffmpeg.

    :arg cfg: конфигурация (пресеты качества).
    :arg kind: вид медиа (image|icon|avatar|video).
    :arg src: путь к оригиналу.
    :arg dst: путь к итоговому файлу.
    :raises ConvertError: при ненулевом коде возврата ffmpeg.
    """
    if kind in _VIDEO_KINDS:
        args = [
            "ffmpeg",
            "-y",
            "-i",
            src,
            "-c:v",
            "libvpx-vp9",
            "-b:v",
            "0",
            "-crf",
            str(cfg.webm_crf),
            "-c:a",
            "libopus",
            "-row-mt",
            "1",
            dst,
        ]
    else:
        args = [
            "ffmpeg",
            "-y",
            "-i",
            src,
            "-c:v",
            "libwebp",
            "-quality",
            str(cfg.webp_quality),
            "-compression_level",
            "6",
            dst,
        ]

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0 or not os.path.exists(dst):
        raise ConvertError(stderr.decode("utf-8", "replace")[-500:] or "ffmpeg failed")


__all__ = ["convert", "target_key", "ConvertError", "_IMAGE_KINDS", "_VIDEO_KINDS"]
