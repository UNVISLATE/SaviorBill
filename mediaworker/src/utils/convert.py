"""Конвертация медиа через ffmpeg.

Вид медиа (изображение/видео) определяется сервером самостоятельно по
сигнатуре байт файла (:func:`detect_kind`) — клиент больше не может его
заявить (раньше был параметр ``kind`` при загрузке, но сигнатура сверялась с
ним только здесь, в фоновой задаче конвертации, уже после приёма файла:
можно было поставить в очередь видео с заявленным ``kind=image`` и заметить
это только когда обработка провалится). Теперь заявленного вида просто нет —
нечему быть неверным.

- ``main`` — сам файл (webp для изображения, webm для видео), всегда один;
- ``thumb`` — маленький квадратный превью-значок; для видео генерируется
  всегда, для изображения — только если оно больше ``media.small_max_bytes``
  (маленькое фото и так уже лёгкий webp, отдельный обрезанный thumb избыточен);
  заменяется целиком при перезаливке (см. ``worker.py::_thumb_replace``) —
  никогда не список;
- ``previews`` — список полнокадровых кадров-постеров (только видео), 0..N;
  при конвертации сразу создаётся один (``preview.<uuid8>``), далее клиент
  может добавлять ещё через ``POST /{token}/preview`` (ручной кадр либо
  случайный, выбранный сервером) — см. ``make_preview()``.

Каждый вариант описывается :class:`Variant` (имя, ключ файла, mime). Имя
``thumb``/``main`` — фиксированный слот (перезаписываемый), имя вида
``preview.<uuid8>`` — стабильный уникальный идентификатор конкретного
превью (не завязан на порядковую позицию в списке — порядок previews[] это
чисто billing-side JSON-массив, переставляемый без переименования файлов).
Размер проставляется вызывающей стороной после записи.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from utils.config import Config

# Коллбэк для realtime-хвоста сырого вывода ffmpeg/ffprobe. Получает очередной сырой
# кусок stderr как есть (не построчно — как реальный терминал, чтобы
# прогресс-строки с ``\r`` тоже воспроизводились в xterm.js один в один).
OutputSink = Callable[[str], Awaitable[None]]


class ConvertError(RuntimeError):
    """Ошибка конвертации ffmpeg."""


class SignatureError(ConvertError):
    """Сигнатура файла не распознана ни как один из известных форматов."""


# Первые байты (magic bytes) известных форматов — дешёвая проверка перед
# запуском ffmpeg (IMPLEMENTATION_PLAN §11.1) и способ определить реальный
# вид медиа без доверия клиенту. Не защита от подделки как таковая (легко
# подделываемая эвристика для откровенно вредоносных файлов), а экономия
# ресурсов на заведомо невалидном файле + автоопределение image/video.
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


def detect_kind(header: bytes) -> str | None:
    """Определить реальный вид медиа по сигнатуре байт.

    :arg header: первые ``SIGNATURE_READ_BYTES`` байт файла.
    :return: ``"image"`` | ``"video"`` | ``None`` (сигнатура не распознана —
        значит либо неизвестный формат, либо мусор/подделка).
    """
    if header.startswith(_RIFF_HEADER):
        fourcc = header[_RIFF_FOURCC_OFFSET : _RIFF_FOURCC_OFFSET + 4]
        if fourcc == _RIFF_IMAGE_FOURCC:
            return "image"
        if fourcc == _RIFF_VIDEO_FOURCC:
            return "video"
        return None
    if _header_matches(header, _IMAGE_SIGNATURES):
        return "image"
    if _header_matches(header, _VIDEO_SIGNATURES):
        return "video"
    return None


@dataclass(slots=True)
class Variant:
    """Один выходной файл конверсии."""

    name: str  # main | preview | preview_thumb
    key: str  # имя файла в хранилище
    mime: str


def target_key(token: str, kind: str) -> tuple[str, str]:
    """Ключ основного файла и его MIME по виду медиа (``image`` | ``video``)."""
    if kind == "video":
        return f"{token}.webm", "video/webm"
    return f"{token}.webp", "image/webp"


def _thumb_vf(size: int) -> str:
    """Фильтр ffmpeg: заполнить квадрат ``size`` и обрезать по центру."""
    return (
        f"scale={size}:{size}:force_original_aspect_ratio=increase,"
        f"crop={size}:{size}"
    )


async def _run(args: list[str], *, on_output: OutputSink | None = None) -> None:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    if on_output is None:
        _, stderr = await proc.communicate()
    else:
        # Читаем сырыми кусками (не readline()) — прогресс ffmpeg обновляет
        # одну строку через "\r" без "\n", readline() завис бы до конца всей
        # задачи. Так каждый кусок форвардится в реалтайме, как в терминале.
        assert proc.stderr is not None
        chunks: list[bytes] = []
        while True:
            chunk = await proc.stderr.read(4096)
            if not chunk:
                break
            chunks.append(chunk)
            await on_output(chunk.decode("utf-8", "replace"))
        await proc.wait()
        stderr = b"".join(chunks)
    dst = args[-1]
    if proc.returncode != 0 or not os.path.exists(dst):
        raise ConvertError(stderr.decode("utf-8", "replace")[-500:] or "ffmpeg failed")


async def probe_duration(src: str) -> float | None:
    """Длительность видео в секундах (``ffprobe``) либо ``None``, если не узнать.

    Нужно для выбора случайного кадра при автогенерации доп. превью
    (``POST /{token}/preview`` с пустым телом — см. ``worker.py::_preview_add``).
    """
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        src,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    try:
        return float(out.decode().strip())
    except (ValueError, UnicodeDecodeError):
        return None


def _webp(src: str, dst: str, quality: int, vf: str | None = None, at: float | None = None) -> list[str]:
    args = ["ffmpeg", "-y"]
    if at is not None:
        args += ["-ss", f"{at:.3f}"]
    args += ["-i", src]
    if vf:
        args += ["-vf", vf]
    args += ["-frames:v", "1", "-c:v", "libwebp", "-quality", str(quality), dst]
    return args


async def convert_image(
    cfg: Config, src: str, out_dir: str, token: str, *, on_output: OutputSink | None = None
) -> list[Variant]:
    """Изображение → только полный webp.

    ``thumb`` для изображения здесь никогда не создаётся — это решает
    вызывающая сторона (``worker.py::_convert``) по фактическому размеру
    результата (маленькие фото не тумбятся, см. модуль-докстринг).
    """
    main = Variant("main", *target_key(token, "image"))
    await _run(_webp(src, os.path.join(out_dir, main.key), cfg.webp_quality), on_output=on_output)
    return [main]


async def make_thumb(
    cfg: Config, src: str, out_dir: str, token: str, *, on_output: OutputSink | None = None
) -> Variant:
    """Собрать (или пересобрать) единственный квадратный thumb медиа."""
    thumb = Variant("thumb", f"{token}.thumb.{uuid.uuid4().hex[:8]}.webp", "image/webp")
    await _run(
        _webp(
            src,
            os.path.join(out_dir, thumb.key),
            cfg.thumb_quality,
            _thumb_vf(cfg.thumb_size),
        ),
        on_output=on_output,
    )
    return thumb


async def make_preview(
    cfg: Config, src: str, out_dir: str, token: str, *, at: float | None = None,
    on_output: OutputSink | None = None,
) -> Variant:
    """Собрать один полнокадровый превью-постер (видео) из кадра ``src``.

    :arg at: смещение в секундах для выбора кадра (``None`` — первый кадр,
        как раньше; для случайного кадра вызывающая сторона сама вычисляет
        и передаёт значение через :func:`probe_duration`).
    :return: :class:`Variant` с именем вида ``preview.<uuid8>`` — стабильный
        уникальный идентификатор, не завязанный на порядковую позицию в
        списке ``previews[]`` (порядок — чисто billing-side JSON, см.
        модуль-докстринг).
    """
    suffix = uuid.uuid4().hex[:8]
    preview = Variant(f"preview.{suffix}", f"{token}.preview.{suffix}.webp", "image/webp")
    await _run(
        _webp(src, os.path.join(out_dir, preview.key), cfg.webp_quality, at=at),
        on_output=on_output,
    )
    return preview


async def convert_video(
    cfg: Config, src: str, out_dir: str, token: str, *, on_output: OutputSink | None = None
) -> list[Variant]:
    """Видео → webm + thumb + один превью-постер по умолчанию."""
    main = Variant("main", *target_key(token, "video"))
    await _run(
        [
            "ffmpeg", "-y", "-i", src,
            "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", str(cfg.webm_crf),
            "-c:a", "libopus", "-row-mt", "1",
            os.path.join(out_dir, main.key),
        ],
        on_output=on_output,
    )
    thumb = await make_thumb(cfg, src, out_dir, token, on_output=on_output)
    preview = await make_preview(cfg, src, out_dir, token, on_output=on_output)
    return [main, thumb, preview]


async def convert(
    cfg: Config, src: str, out_dir: str, token: str, *, on_output: OutputSink | None = None
) -> tuple[str, list[Variant]]:
    """Определить вид медиа и сконвертировать оригинал во все варианты.

    :arg cfg: конфигурация (пресеты качества).
    :arg src: путь к оригиналу.
    :arg out_dir: каталог для выходных файлов.
    :arg token: идентификатор медиа (префикс имён файлов).
    :arg on_output: коллбэк сырого вывода ffmpeg/ffprobe для realtime-лога
        (см. ``utils/proclog.py``); ``None`` — не логировать (например,
        служебные вызовы без активного WS-слушателя).
    :return: ``(detected_kind, variants)`` — ``detected_kind`` — фактический
        вид медиа (``"image"`` | ``"video"``), определённый по сигнатуре, а
        не заявленный клиентом; ``variants[0]`` всегда ``main``.
    :raises SignatureError: сигнатура не распознана ни как один из известных
        форматов (мусор/повреждённый файл/то, что мы не конвертируем).
    :raises ConvertError: при ненулевом коде возврата ffmpeg.
    """
    with open(src, "rb") as fh:
        header = fh.read(SIGNATURE_READ_BYTES)
    kind = detect_kind(header)
    if kind is None:
        raise SignatureError("файл не распознан: неизвестная сигнатура")
    if kind == "video":
        return kind, await convert_video(cfg, src, out_dir, token, on_output=on_output)
    return kind, await convert_image(cfg, src, out_dir, token, on_output=on_output)


__all__ = [
    "convert",
    "convert_image",
    "convert_video",
    "make_thumb",
    "make_preview",
    "probe_duration",
    "detect_kind",
    "target_key",
    "Variant",
    "ConvertError",
    "SignatureError",
    "SIGNATURE_READ_BYTES",
]
