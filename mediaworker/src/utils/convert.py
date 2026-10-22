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
import re
import shutil
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
SIGNATURE_READ_BYTES = 256


def _header_matches(header: bytes, signatures: list[tuple[bytes, int]]) -> bool:
    return any(
        header[offset : offset + len(sig)] == sig for sig, offset in signatures
    )


async def sniff_and_rewind(stream, want: int = SIGNATURE_READ_BYTES):  # noqa: ANN001
    """Прочитать первые ``want`` байт асинхронного потока байт (тело HTTP-запроса)
    для определения реального типа файла ДО записи на диск (см. AUDIT.md
    §4.1/§4.2), не теряя прочитанные куски — возвращает их вместе с
    итератором, продолжающим отдавать тело как ни в чём не бывало.
    """
    buf = bytearray()
    buffered: list[bytes] = []
    async for chunk in stream:
        buffered.append(chunk)
        buf.extend(chunk)
        if len(buf) >= want:
            break

    async def _rewound():
        for c in buffered:
            yield c
        async for c in stream:
            yield c

    return bytes(buf[:want]), _rewound()


def is_svg(header: bytes) -> bool:
    h = header.strip()
    return h.startswith(b"<svg") or h.startswith(b"<?xml") or b"<svg" in h[:256]


def is_gif(header: bytes) -> bool:
    return header.startswith(b"GIF87a") or header.startswith(b"GIF89a")


def detect_kind(header: bytes) -> str | None:
    """Определить реальный вид медиа по сигнатуре байт.

    :arg header: первые ``SIGNATURE_READ_BYTES`` байт файла.
    :return: ``"image"`` | ``"video"`` | ``"svg"`` | ``None``.
    """
    if is_svg(header):
        return "svg"
    if is_gif(header):
        return "image" 
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


def sanitize_paths(text: str, *dirs: str) -> str:
    """Замаскировать абсолютные пути сервера в сыром выводе ffmpeg/ffprobe
    перед показом клиенту (см. AUDIT.md §4.4) — stderr обычно содержит полный
    путь к input/output файлам (``uploads_dir``/``media_dir``), лишняя
    диагностика для права ``system.jobs.read``."""
    out = text
    for d in dirs:
        if not d:
            continue
        out = out.replace(d, "<mediaworker>")
    return out


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
        "-show_entries", "format=duration,bit_rate,format_name",
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
    fmt = probe.get("format") or {}
    if fmt.get("format_name"):
        meta["format_name"] = fmt["format_name"]
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
    else:
        args += ["-ss", "0.000"]
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
    vf: str | None = None,
    on_output: OutputSink | None = None,
) -> Variant:
    suffix = uuid.uuid4().hex[:8]
    preview = Variant(f"preview.{suffix}", f"{token}.preview.{suffix}.webp", "image/webp")
    await _run(
        _webp(src, os.path.join(out_dir, preview.key), cfg.webp_quality, vf=vf, at=at),
        on_output=on_output,
    )
    return preview


VALID_VIDEO_PRESETS: set[str] = {
    "ultrafast",
    "superfast",
    "veryfast",
    "faster",
    "fast",
    "medium",
    "slow",
    "slower",
    "veryslow",
}
VALID_AUDIO_BITRATE_RE = re.compile(r"^\d{2,4}k$")


def _parse_scale_filter(scale_str: str | None, for_poster: bool = False) -> str | None:
    if not scale_str or scale_str.lower() in ("original", "none", "off", ""):
        return None
    s = scale_str.strip().lower()

    preset_dims = {
        "2160p": (3840, 2160),
        "4k": (3840, 2160),
        "1440p": (2560, 1440),
        "2k": (2560, 1440),
        "1080p": (1920, 1080),
        "fhd": (1920, 1080),
        "720p": (1280, 720),
        "hd": (1280, 720),
        "480p": (854, 480),
        "sd": (854, 480),
        "360p": (640, 360),
    }

    if s in preset_dims:
        max_w, max_h = preset_dims[s]
        if for_poster:
            return f"scale='min({max_w},iw)':-2"
        return f"scale=-2:'min({max_h},ih)'"

    # Pattern: <number>p e.g. 1200p or 900p
    m_p = re.match(r"^(\d{3,4})p$", s)
    if m_p:
        h = int(m_p.group(1))
        w = int(h * 16 / 9)
        if for_poster:
            return f"scale='min({w},iw)':-2"
        return f"scale=-2:'min({h},ih)'"

    # Pattern: <W>x<H> e.g. 1920x1080 or 1280x720
    m_dim = re.match(r"^(\d{2,4})x(\d{2,4})$", s)
    if m_dim:
        w = int(m_dim.group(1))
        h = int(m_dim.group(2))
        if for_poster:
            return f"scale='min({w},iw)':-2"
        return f"scale=-2:'min({h},ih)'"

    return None


async def convert_video(
    cfg: Config,
    src: str,
    out_dir: str,
    token: str,
    *,
    video_codec: str = "copy",
    audio_codec: str = "copy",
    format_choice: str = "original",
    scale: str = "original",
    poster_scale: str = "original",
    crf: int | None = None,
    cpu_used: int | None = None,
    video_preset: str | None = None,
    audio_bitrate: str | None = None,
    on_output: OutputSink | None = None,
    on_progress: ProgressSink | None = None,
    on_stage: StageSink | None = None,
) -> list[Variant]:
    """Видео → webm/mp4 + thumb + один превью-постер по умолчанию."""
    vf_poster = _parse_scale_filter(poster_scale, for_poster=True)

    if video_codec == "copy" or format_choice == "original":
        meta = await probe_media(src)
        ext = "mp4"
        mime = "video/mp4"
        fmt_name = (meta.get("format_name") or "").lower()
        if "webm" in fmt_name or "matroska" in fmt_name or src.endswith(".webm"):
            ext = "webm"
            mime = "video/webm"
        main = Variant("main", f"{token}.{ext}", mime)
        shutil.copyfile(src, os.path.join(out_dir, main.key))
        if on_stage:
            await on_stage("thumb")
        thumb = await make_thumb(cfg, src, out_dir, token, on_output=on_output)
        if on_stage:
            await on_stage("preview")
        preview = await make_preview(cfg, src, out_dir, token, vf=vf_poster, on_output=on_output)
        return [main, thumb, preview]

    target_ext = "mp4" if format_choice == "mp4" else "webm"
    target_mime = "video/mp4" if format_choice == "mp4" else "video/webm"
    main = Variant("main", f"{token}.{target_ext}", target_mime)

    vf_filters = []
    scale_filter = _parse_scale_filter(scale, for_poster=False)
    if scale_filter:
        vf_filters.append(scale_filter)

    duration = await probe_duration(src) if on_progress is not None else None
    if on_stage:
        await on_stage("encode")

    cmd = ["ffmpeg", "-y", "-i", src]
    if vf_filters:
        cmd += ["-vf", ",".join(vf_filters)]

    eff_preset = video_preset if (video_preset and video_preset in VALID_VIDEO_PRESETS) else "veryfast"
    eff_audio_bitrate = audio_bitrate if (audio_bitrate and VALID_AUDIO_BITRATE_RE.match(audio_bitrate)) else "128k"

    if target_ext == "mp4" or video_codec == "libx264":
        crf_val = crf if crf is not None else 23
        cmd += ["-c:v", "libx264", "-crf", str(crf_val), "-preset", eff_preset]
        if audio_codec == "none":
            cmd += ["-an"]
        elif audio_codec == "copy":
            cmd += ["-c:a", "copy"]
        else:
            cmd += ["-c:a", "aac", "-b:a", eff_audio_bitrate]
        cmd += ["-movflags", "+faststart"]
    else:
        crf_val = crf if crf is not None else (cfg.webm_crf or 32)
        cpu_val = cpu_used if cpu_used is not None else 8
        cmd += [
            "-c:v", "libvpx-vp9", "-b:v", "0",
            "-crf", str(crf_val),
            "-deadline", "good",
            "-cpu-used", str(cpu_val),
            "-pix_fmt", "yuv420p",
        ]
        if audio_codec == "none":
            cmd += ["-an"]
        elif audio_codec == "copy":
            cmd += ["-c:a", "copy"]
        else:
            cmd += ["-c:a", "libopus", "-b:a", eff_audio_bitrate]
        cmd += ["-row-mt", "1"]

    cmd.append(os.path.join(out_dir, main.key))
    await _run(
        cmd,
        on_output=on_output,
        on_progress=on_progress,
        total_duration=duration,
    )
    if on_stage:
        await on_stage("thumb")
    thumb = await make_thumb(cfg, src, out_dir, token, on_output=on_output)
    if on_stage:
        await on_stage("preview")
    preview = await make_preview(cfg, src, out_dir, token, vf=vf_poster, on_output=on_output)
    return [main, thumb, preview]


async def convert(
    cfg: Config,
    src: str,
    out_dir: str,
    token: str,
    *,
    video_codec: str = "copy",
    audio_codec: str = "copy",
    format_choice: str = "original",
    scale: str = "original",
    poster_scale: str = "original",
    crf: int | None = None,
    keep_animation: bool = True,
    cpu_used: int | None = None,
    video_preset: str | None = None,
    audio_bitrate: str | None = None,
    on_output: OutputSink | None = None,
    on_progress: ProgressSink | None = None,
    on_stage: StageSink | None = None,
) -> tuple[str, list[Variant]]:
    """Определить вид медиа и сконвертировать оригинал во все варианты."""
    with open(src, "rb") as fh:
        header = fh.read(SIGNATURE_READ_BYTES)
    kind = detect_kind(header)
    if kind is None:
        raise SignatureError("файл не распознан: неизвестная сигнатура")

    if kind == "svg":
        dst = os.path.join(out_dir, f"{token}.svg")
        shutil.copyfile(src, dst)
        return "image", [Variant("main", f"{token}.svg", "image/svg+xml")]

    if is_gif(header):
        if format_choice == "webm":
            return "video", await convert_video(
                cfg,
                src,
                out_dir,
                token,
                video_codec="libvpx-vp9",
                audio_codec="none",
                format_choice="webm",
                scale=scale,
                poster_scale=poster_scale,
                crf=crf,
                on_output=on_output,
                on_progress=on_progress,
                on_stage=on_stage,
            )
        if format_choice == "webp" or not keep_animation:
            return "image", await convert_image(cfg, src, out_dir, token, on_output=on_output)

        # Default: keep original animated GIF!
        dst = os.path.join(out_dir, f"{token}.gif")
        shutil.copyfile(src, dst)
        main = Variant("main", f"{token}.gif", "image/gif")
        thumb = await make_thumb(cfg, src, out_dir, token, on_output=on_output)
        return "image", [main, thumb]

    if kind == "video":
        return kind, await convert_video(
            cfg,
            src,
            out_dir,
            token,
            video_codec=video_codec,
            audio_codec=audio_codec,
            format_choice=format_choice,
            scale=scale,
            poster_scale=poster_scale,
            crf=crf,
            cpu_used=cpu_used,
            video_preset=video_preset,
            audio_bitrate=audio_bitrate,
            on_output=on_output,
            on_progress=on_progress,
            on_stage=on_stage,
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
    "is_svg",
    "is_gif",
    "target_key",
    "Variant",
    "ConvertError",
    "SignatureError",
    "SIGNATURE_READ_BYTES",
]
