"""Конвертация медиа через ffmpeg.

Вид медиа определяется сервером по сигнатуре байт (:func:`detect_kind`), не
клиентским параметром — иначе можно поставить видео в очередь с заявленным
``kind=image`` и проверка расходится с реальным содержимым только на этапе
обработки. ``main``/``thumb`` — фиксированные перезаписываемые слоты; каждый
``preview.<uuid8>`` — стабильный id, не завязанный на позицию в списке.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from utils.config import Config
from utils.ffprogress import ProgressParser, ProgressSnapshot

# Коллбэк для realtime-хвоста сырого вывода ffmpeg/ffprobe. Получает очередной сырой
# кусок stderr как есть (не построчно — как реальный терминал, чтобы
# прогресс-строки с ``\r`` тоже воспроизводились в xterm.js один в один).
OutputSink = Callable[[str], Awaitable[None]]

# Коллбэк снимка машинно-читаемого прогресса (``-progress pipe:1``) — процент/
# ETA/fps, не сырой текст (см. utils/ffprogress.py).
ProgressSink = Callable[[ProgressSnapshot], Awaitable[None]]

# Коллбэк смены под-этапа многошаговой конвертации (``"encode"``/``"thumb"``/
# ``"preview"``) — см. ``utils/proclog.py::set_stage``. Отдельно от ``on_output``/
# ``on_progress``: это не вывод процесса, а факт "какой именно шаг сейчас
# выполняется", нужный, чтобы период между 100% прогресса кодирования и
# итоговым ``ready`` не выглядел как "зависший" running-job без объяснения.
StageSink = Callable[[str], Awaitable[None]]


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


async def _run(
    args: list[str],
    *,
    on_output: OutputSink | None = None,
    on_progress: ProgressSink | None = None,
    total_duration: float | None = None,
) -> None:
    # ``-progress pipe:1 -nostats`` — машинно-читаемый прогресс на stdout,
    # не мешает человеческому логу на stderr (для on_output/xterm.js).
    run_args = [args[0], "-progress", "pipe:1", "-nostats", *args[1:]] if on_progress else args
    proc = await asyncio.create_subprocess_exec(
        *run_args,
        stdout=asyncio.subprocess.PIPE if on_progress else asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stderr is not None

    async def _pump_stderr() -> bytes:
        if on_output is None:
            return await proc.stderr.read()
        # Читаем сырыми кусками (не readline()) — прогресс-бар ffmpeg
        # обновляет одну строку через "\r" без "\n", readline() завис бы до
        # конца всей задачи. Так каждый кусок форвардится в реалтайме, как
        # в терминале.
        chunks: list[bytes] = []
        while True:
            chunk = await proc.stderr.read(4096)
            if not chunk:
                break
            chunks.append(chunk)
            await on_output(chunk.decode("utf-8", "replace"))
        return b"".join(chunks)

    async def _pump_progress() -> None:
        if on_progress is None or proc.stdout is None:
            return
        parser = ProgressParser(total_duration)
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            snapshot = parser.feed_line(line.decode("utf-8", "replace"))
            if snapshot is not None:
                await on_progress(snapshot)

    stderr_task = asyncio.create_task(_pump_stderr())
    progress_task = asyncio.create_task(_pump_progress())
    await proc.wait()
    stderr = await stderr_task
    await progress_task
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


async def probe_media(src: str) -> dict:
    """Технические метаданные готового файла (``system_media.meta``, см.
    IMPLEMENTATION_PLAN.md §5.7) — только технические поля (без EXIF/geo):
    ``width``/``height`` для всех, плюс ``duration_sec``/``codec``/``fps``/
    ``bitrate`` для видео. Одним вызовом ``ffprobe -show_streams -show_format``
    (JSON) — тот же инструмент, что уже используется в проекте
    (:func:`probe_duration`), не тянем отдельную библиотеку (Pillow/exiftool)
    просто для width/height.

    Best-effort: пустой словарь при ошибке разбора — метаданные не входят в
    контракт "готово/не готово" самой конвертации, отсутствие не должно ронять
    ``_convert()`` (тот же принцип, что и у ``progress_sink``, см. ``worker.py``).
    """
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error",
        "-show_entries", "stream=width,height,codec_type,codec_name,r_frame_rate,bit_rate",
        "-show_entries", "format=duration,bit_rate",
        "-of", "json",
        src,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    try:
        probe = json.loads(out.decode())
    except (ValueError, UnicodeDecodeError):
        return {}

    meta: dict = {}
    video_stream = next(
        (s for s in probe.get("streams") or [] if s.get("codec_type") == "video"), None
    )
    if video_stream:
        if video_stream.get("width"):
            meta["width"] = video_stream["width"]
        if video_stream.get("height"):
            meta["height"] = video_stream["height"]
        if video_stream.get("codec_name"):
            meta["codec"] = video_stream["codec_name"]
        rate = video_stream.get("r_frame_rate")  # "30/1" | "30000/1001" | "0/0"
        if rate and "/" in rate:
            num, _, den = rate.partition("/")
            try:
                if float(den):
                    meta["fps"] = round(float(num) / float(den), 2)
            except ValueError:
                pass
        bitrate = video_stream.get("bit_rate") or (probe.get("format") or {}).get("bit_rate")
        if bitrate:
            try:
                meta["bitrate"] = int(bitrate)
            except ValueError:
                pass
    duration = (probe.get("format") or {}).get("duration")
    if duration:
        try:
            meta["duration_sec"] = round(float(duration), 1)
        except ValueError:
            pass
    return meta


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
    cfg: Config,
    src: str,
    out_dir: str,
    token: str,
    *,
    on_output: OutputSink | None = None,
    on_progress: ProgressSink | None = None,
    on_stage: StageSink | None = None,
) -> list[Variant]:
    """Видео → webm + thumb + один превью-постер по умолчанию.

    ``on_progress`` — только для основного кодирования (webm): это единственный
    шаг, который может идти минутами; thumb/preview — вырезка одного кадра,
    процент/ETA для них не осмыслены. ``on_stage`` уведомляет о переходе между
    шагами (``encode``/``thumb``/``preview``), чтобы клиент видел, чем занят
    job, даже когда процент/ETA для текущего шага не публикуются.
    """
    main = Variant("main", *target_key(token, "video"))
    duration = await probe_duration(src) if on_progress is not None else None
    if on_stage:
        await on_stage("encode")
    await _run(
        [
            "ffmpeg", "-y", "-i", src,
            "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", str(cfg.webm_crf),
            "-deadline", "good", "-cpu-used", str(cfg.webm_cpu_used),
            "-c:a", "libopus", "-row-mt", "1",
            os.path.join(out_dir, main.key),
        ],
        on_output=on_output,
        on_progress=on_progress,
        total_duration=duration,
    )
    if on_stage:
        await on_stage("thumb")
    thumb = await make_thumb(cfg, src, out_dir, token, on_output=on_output)
    if on_stage:
        await on_stage("preview")
    preview = await make_preview(cfg, src, out_dir, token, on_output=on_output)
    return [main, thumb, preview]


async def convert(
    cfg: Config,
    src: str,
    out_dir: str,
    token: str,
    *,
    on_output: OutputSink | None = None,
    on_progress: ProgressSink | None = None,
    on_stage: StageSink | None = None,
) -> tuple[str, list[Variant]]:
    """Определить вид медиа и сконвертировать оригинал во все варианты.

    :arg cfg: конфигурация (пресеты качества).
    :arg src: путь к оригиналу.
    :arg out_dir: каталог для выходных файлов.
    :arg token: идентификатор медиа (префикс имён файлов).
    :arg on_output: коллбэк сырого вывода ffmpeg/ffprobe для realtime-лога
        (см. ``utils/proclog.py``); ``None`` — не логировать (например,
        служебные вызовы без активного WS-слушателя).
    :arg on_progress: коллбэк снимка процента/ETA основного видео-кодирования
        (см. ``utils/ffprogress.py``); для изображений не используется —
        конвертация одним кадром слишком быстрая, чтобы это было осмысленно.
    :arg on_stage: коллбэк смены под-этапа (``encode``/``thumb``/``preview``
        для видео); для изображений не вызывается — один шаг, стадия не нужна.
    :return: ``(detected_kind, variants)`` — ``detected_kind`` — фактический
        вид медиа (``"image"`` | ``"video"``), определённый по сигнатуре, а
        не заявленный клиентом; ``variants[0]`` всегда ``main``.
    :raises SignatureError: сигнатура файла не распознана ни как один из
        известных форматов (мусор/повреждённый файл/то, что мы не конвертируем).
    :raises ConvertError: при ненулевом коде возврата ffmpeg.
    """
    with open(src, "rb") as fh:
        header = fh.read(SIGNATURE_READ_BYTES)
    kind = detect_kind(header)
    if kind is None:
        raise SignatureError("файл не распознан: неизвестная сигнатура")
    if kind == "video":
        return kind, await convert_video(
            cfg, src, out_dir, token, on_output=on_output, on_progress=on_progress, on_stage=on_stage
        )
    return kind, await convert_image(cfg, src, out_dir, token, on_output=on_output)


__all__ = [
    "convert",
    "convert_image",
    "convert_video",
    "make_thumb",
    "make_preview",
    "probe_duration",
    "probe_media",
    "detect_kind",
    "target_key",
    "Variant",
    "ConvertError",
    "SignatureError",
    "SIGNATURE_READ_BYTES",
]
