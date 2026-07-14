"""Конвертация медиа через ffmpeg.

Из одного оригинала генерируется несколько вариантов:

- изображение → только ``main`` (webp, уже оптимизированный формат — отдельный
  обрезанный thumb для фото избыточен, т.к. оригинал и так лёгкий webp);
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


class SignatureError(ConvertError):
    """Сигнатура файла не соответствует заявленному виду медиа."""


# Первые байты (magic bytes) известных форматов — дешёвая проверка перед
# запуском ffmpeg (IMPLEMENTATION_PLAN §11.1). Не защита от подделки как
# таковая (легко подделываемая эвристика), а экономия ресурсов на заведомо
# невалидном/не том файле: сразу отказ без запуска внешнего процесса.
# Формат записи: (сигнатура, смещение в байтах).
_IMAGE_SIGNATURES: list[tuple[bytes, int]] = [
    (b"\xff\xd8\xff", 0),  # JPEG
    (b"\x89PNG\r\n\x1a\n", 0),  # PNG
    (b"GIF87a", 0),  # GIF
    (b"GIF89a", 0),  # GIF
    (b"BM", 0),  # BMP
]
_VIDEO_SIGNATURES: list[tuple[bytes, int]] = [
    (b"ftyp", 4),  # MP4/MOV/... (ISO base media file format)
    (b"\x1aE\xdf\xa3", 0),  # WebM/MKV (Matroska/EBML)
    (b"OggS", 0),  # OGG
]
# RIFF-контейнер общий для нескольких форматов — fourCC на смещении 8
# определяет реальный формат (WEBP → image, AVI → video).
_RIFF_HEADER = b"RIFF"
_RIFF_FOURCC_OFFSET = 8
_RIFF_IMAGE_FOURCC = b"WEBP"
_RIFF_VIDEO_FOURCC = b"AVI "

# Сколько байт заголовка достаточно прочитать для проверки всех сигнатур выше.
SIGNATURE_READ_BYTES = 16


def _header_matches(header: bytes, signatures: list[tuple[bytes, int]]) -> bool:
    return any(
        header[offset : offset + len(sig)] == sig for sig, offset in signatures
    )


def check_signature(kind: str, header: bytes) -> None:
    """Сверить первые байты файла с magic bytes заявленного вида медиа.

    :arg kind: вид медиа (image|icon|avatar|video).
    :arg header: первые ``SIGNATURE_READ_BYTES`` байт файла.
    :raises SignatureError: сигнатура не распознана как ни один из известных
        форматов данного вида — экономим ffmpeg-вызов на заведомо невалидном
        (или не том) файле.
    """
    is_video = kind in _VIDEO_KINDS
    if header.startswith(_RIFF_HEADER):
        fourcc = header[_RIFF_FOURCC_OFFSET : _RIFF_FOURCC_OFFSET + 4]
        expected = _RIFF_VIDEO_FOURCC if is_video else _RIFF_IMAGE_FOURCC
        if fourcc == expected:
            return
        raise SignatureError(
            f"файл не распознан как {kind}: RIFF-контейнер не того формата"
        )
    signatures = _VIDEO_SIGNATURES if is_video else _IMAGE_SIGNATURES
    if not _header_matches(header, signatures):
        raise SignatureError(
            f"файл не распознан как {kind}: неизвестная сигнатура"
        )


@dataclass(slots=True)
class Variant:
    """Один выходной файл конверсии."""

    name: str  # main | preview | preview_thumb
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
    """Изображение → только полный webp (thumb не генерируется — избыточно)."""
    main = Variant("main", *target_key(token, "image"))
    await _run(_webp(src, os.path.join(out_dir, main.key), cfg.webp_quality))
    return [main]


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
    :raises SignatureError: сигнатура файла не соответствует заявленному виду.
    :raises ConvertError: при ненулевом коде возврата ffmpeg.
    """
    with open(src, "rb") as fh:
        header = fh.read(SIGNATURE_READ_BYTES)
    check_signature(kind, header)
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
    "SignatureError",
    "check_signature",
    "SIGNATURE_READ_BYTES",
    "_IMAGE_KINDS",
    "_VIDEO_KINDS",
]
