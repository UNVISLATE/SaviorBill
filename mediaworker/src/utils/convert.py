"""Конвертация медиа через ffmpeg.

Из одного оригинала генерируется несколько вариантов:

- изображение → ``main`` (webp, полное качество) + ``thumb`` (webp, обрезанный
  квадрат минимального качества/размера);
- видео → ``main`` (webm) + ``preview`` (полный кадр-постер, webp) +
  ``preview_thumb`` (обрезанный мини-постер, webp).

Каждый вариант описывается :class:`Variant` (имя, ключ файла, mime). Размер
проставляется вызывающей стороной после записи.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from utils.config import Config

_IMAGE_KINDS = {"image", "icon", "avatar"}
_VIDEO_KINDS = {"video"}


class ConvertError(RuntimeError):
    """Ошибка конвертации ffmpeg."""


@dataclass(slots=True)
class Variant:
    """Один выходной файл конверсии."""

    name: str  # main | thumb | preview | preview_thumb
    key: str  # имя файла в хранилище
    mime: str


def target_key(token: str, kind: str) -> tuple[str, str]:
    """Ключ основного файла и его MIME по виду медиа."""
    if kind in _VIDEO_KINDS:
        return f"{token}.webm", "video/webm"
    return f"{token}.webp", "image/webp"


def _thumb_vf(size: int) -> str:
    """Фильтр ffmpeg: заполнить квадрат ``size`` и обрезать по центру."""
    return (
        f"scale={size}:{size}:force_original_aspect_ratio=increase,"
        f"crop={size}:{size}"
    )


async def _run(args: list[str]) -> None:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    dst = args[-1]
    if proc.returncode != 0 or not os.path.exists(dst):
        raise ConvertError(stderr.decode("utf-8", "replace")[-500:] or "ffmpeg failed")


def _webp(src: str, dst: str, quality: int, vf: str | None = None) -> list[str]:
    args = ["ffmpeg", "-y", "-i", src]
    if vf:
        args += ["-vf", vf]
    args += ["-frames:v", "1", "-c:v", "libwebp", "-quality", str(quality), dst]
    return args


async def convert_image(
    cfg: Config, src: str, out_dir: str, token: str
) -> list[Variant]:
    """Изображение → полный webp + обрезанный мини-webp."""
    main = Variant("main", *target_key(token, "image"))
    thumb = Variant("thumb", f"{token}.thumb.webp", "image/webp")
    await _run(_webp(src, os.path.join(out_dir, main.key), cfg.webp_quality))
    await _run(
        _webp(
            src,
            os.path.join(out_dir, thumb.key),
            cfg.thumb_quality,
            _thumb_vf(cfg.thumb_size),
        )
    )
    return [main, thumb]


async def convert_video(
    cfg: Config, src: str, out_dir: str, token: str, *, make_preview: bool = True
) -> list[Variant]:
    """Видео → webm + (опционально) полный и мини-постеры."""
    main = Variant("main", *target_key(token, "video"))
    await _run(
        [
            "ffmpeg", "-y", "-i", src,
            "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", str(cfg.webm_crf),
            "-c:a", "libopus", "-row-mt", "1",
            os.path.join(out_dir, main.key),
        ]
    )
    variants = [main]
    if make_preview:
        variants += await make_video_preview(cfg, src, out_dir, token)
    return variants


async def make_video_preview(
    cfg: Config, src: str, out_dir: str, token: str
) -> list[Variant]:
    """Собрать полный и мини-постеры из кадра ``src`` (кадр видео или картинка)."""
    preview = Variant("preview", f"{token}.preview.webp", "image/webp")
    preview_thumb = Variant(
        "preview_thumb", f"{token}.preview_thumb.webp", "image/webp"
    )
    await _run(_webp(src, os.path.join(out_dir, preview.key), cfg.webp_quality))
    await _run(
        _webp(
            src,
            os.path.join(out_dir, preview_thumb.key),
            cfg.thumb_quality,
            _thumb_vf(cfg.thumb_size),
        )
    )
    return [preview, preview_thumb]


async def convert(
    cfg: Config, kind: str, src: str, out_dir: str, token: str
) -> list[Variant]:
    """Сконвертировать оригинал во все варианты по виду медиа.

    :arg cfg: конфигурация (пресеты качества).
    :arg kind: вид медиа (image|icon|avatar|video).
    :arg src: путь к оригиналу.
    :arg out_dir: каталог для выходных файлов.
    :arg token: идентификатор медиа (префикс имён файлов).
    :return: список вариантов (``main`` всегда первый).
    :raises ConvertError: при ненулевом коде возврата ffmpeg.
    """
    if kind in _VIDEO_KINDS:
        return await convert_video(cfg, src, out_dir, token)
    return await convert_image(cfg, src, out_dir, token)


__all__ = [
    "convert",
    "convert_image",
    "convert_video",
    "make_video_preview",
    "target_key",
    "Variant",
    "ConvertError",
    "_IMAGE_KINDS",
    "_VIDEO_KINDS",
]
