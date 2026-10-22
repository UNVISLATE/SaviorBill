"""Двухшаговая загрузка медиа.

Шаг 1: ``POST /api/media/upload``
  — проверяет JWT и права, возвращает одноразовый upload-token (TTL 1 мин).
  Вид медиа (image/video) больше не передаётся клиентом — сервер сам
  определяет его по сигнатуре файла при конвертации (см. ``utils/convert.py``);
  раньше заявленный клиентом ``kind`` не проверялся при приёме, только в
  фоновой задаче конвертации — можно было поставить в очередь видео с
  ``kind=image``. Вместо ``kind`` можно передать необязательный ``tag`` —
  короткая метка для админки/клиента (см. ``_TAG_RE``), никак не влияющая на
  обработку файла.

Шаг 2: ``POST /api/media/upload/{upload_token}``
  — принимает файл-стрим по токену; в БД не ходит.
"""

from __future__ import annotations

import re
import time
import uuid
import asyncio
import logging

import valkey.asyncio as valkey
from valkey.exceptions import ValkeyError
from fastapi import APIRouter, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials

from utils import ipban
from utils.authctx import authenticate, authorize, client_ip
from utils.bus_sign import sign_fields
from utils.config import Config
from utils.convert import SIGNATURE_READ_BYTES, detect_kind, sniff_and_rewind
from utils.keys import rate_key, status_key, step2_rate_key, uptoken_key
from utils.rbac import has_perm
from utils.openapi_auth import bearer_scheme
from utils.settings import SettingsResolver
from utils.storage import Storage
from utils.task_log import TaskLog
from utils.telemetry import inject_carrier

log = logging.getLogger("saviormedia.upload")
VALKEY_ERRORS: tuple[type[BaseException], ...] = (
    ValkeyError,
    OSError,
    asyncio.TimeoutError,
)


def note_degraded(component: str, exc: BaseException) -> None:
    log.warning("valkey unavailable, %s degraded: %s", component, exc)

router = APIRouter()

_PERM_SMALL = "media.upload.image"
_PERM_LARGE = "media.upload.video"
# Админское право без ограничений по размеру вообще (не совпадает с
# _PERM_LARGE, у которого есть потолок MEDIA_MAX_BYTES — см. §2.2 AUDIT.md).
_PERM_ADMIN_UNLIMITED = "admin.media.upload"
# Достаточно большой предел, чтобы Storage.save_stream не приходилось учить
# понимать "без лимита"; реального файла такого размера на диске не будет.
_UNLIMITED_BYTES = 2**62
# Лимит попыток шага 2 (приём файла) на один IP в минуту — независимо от
# часового лимита шага 1 (тот считает по аккаунту, этот — по IP, чтобы не
# пускать перебор чужих/просроченных upload-token'ов и общий флуд запросами).
_STEP2_RATE_PER_MIN = 30
# До 16 символов, только латиница и цифры — просто метка для UI, не влияет
# на обработку файла (в отличие от прежнего "kind").
_TAG_RE = re.compile(r"^[A-Za-z0-9]{1,16}$")

# Пресеты скорости/качества VP9 (см. IMPLEMENTATION_PLAN.md §1.5): значение —
# cpu-used для libvpx-vp9 (0 — медленнее/лучше качество, 8 — быстрее/хуже).
# media.upload.video всегда получает "fast" (пользователи с большими файлами не
# должны иметь возможность выбрать медленный пресет и забить очередь конвертации
# надолго); admin.media.upload может выбрать любой + переопределить CRF.
_VIDEO_PRESETS: dict[str, int] = {"fast": 8, "balanced": 5, "quality": 2}
_DEFAULT_PRESET = "balanced"

_VALID_SCALE_RE = re.compile(
    r"^(?:original|none|2160p|4k|1440p|2k|1080p|fhd|720p|hd|480p|sd|360p|\d{3,4}p|\d{2,4}x\d{2,4})$",
    re.IGNORECASE,
)
_VALID_AUDIO_BITRATE_RE = re.compile(r"^\d{2,4}k$", re.IGNORECASE)
_VALID_FFMPEG_PRESETS: set[str] = {
    "ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"
}


def _valkey_unavailable(exc: BaseException) -> HTTPException:
    note_degraded("media_upload", exc)
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "media service temporarily unavailable",
        headers={"Retry-After": "5"},
    )

# Атомарный claim одноразового upload-token: HGETALL + DEL одним вызовом.
_CLAIM_TOKEN_SCRIPT = """
local data = redis.call('HGETALL', KEYS[1])
if #data == 0 then return nil end
redis.call('DEL', KEYS[1])
return data
"""


async def _enforce_hourly_limit(
    request: Request, acc_id: int, perms: dict | None
) -> None:
    """Лимит загрузок в час для обычных пользователей (кроме media.upload.video
    и admin.media.upload)."""
    if has_perm(perms, _PERM_LARGE) or has_perm(perms, _PERM_ADMIN_UNLIMITED):
        return
    settings: SettingsResolver = request.app.state.settings
    vk: valkey.Valkey = request.app.state.vk
    bucket = int(time.time()) // 3600
    key = rate_key(acc_id, bucket)
    used = await vk.incr(key)
    if used == 1:
        await vk.expire(key, 3600)
    limit = await settings.uploads_per_hour()
    if used > limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "upload rate limit exceeded"
        )


async def _enforce_media_count_limit(
    request: Request, acc_id: int, perms: dict | None
) -> None:
    """Лимит количества медиа-файлов на аккаунт (``user.media.limit``).

    Жёсткий отказ при превышении — без авто-удаления старых файлов
    (пользователь должен сам удалить что-то, чтобы загрузить новое).
    Не применяется к правам, снимающим ограничение размера (media.upload.video/
    admin.media.upload) — те же роли, что не упираются в размер файла, не
    должны упираться и в счётчик.
    """
    if has_perm(perms, _PERM_LARGE) or has_perm(perms, _PERM_ADMIN_UNLIMITED):
        return
    settings: SettingsResolver = request.app.state.settings
    db = request.app.state.db
    limit = await settings.user_media_limit()
    count = await db.media_count_for_owner(acc_id)
    if count >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"media count limit reached ({limit}); delete something first",
        )


async def _enforce_storage_quota(
    request: Request, acc_id: int, perms: dict | None
) -> None:
    """Суммарный объём (байт) уже сохранённых медиа не должен превышать квоту.

    В отличие от лимита размера ОДНОГО файла, это лимит на ОБЩИЙ объём —
    раньше он отсутствовал для ``media.upload.video`` вообще (см. AUDIT.md
    §1.4 HIGH-2), позволяя копить неограниченное число файлов по 500 MiB
    каждый. ``admin.media.upload`` остаётся без потолка — это единственное
    по-настоящему безлимитное право.

    Проверяется здесь предварительно (по уже сохранённым файлам — точный
    итоговый размер нового файла после конвертации ещё не известен), финальная
    проверка — в mediaworker после конвертации (см. ``utils/worker.py::
    _convert``), где точный размер уже есть.
    """
    if has_perm(perms, _PERM_ADMIN_UNLIMITED):
        return
    settings: SettingsResolver = request.app.state.settings
    db = request.app.state.db
    is_large = has_perm(perms, _PERM_LARGE)
    quota = (
        await settings.quota_video_bytes()
        if is_large
        else await settings.quota_image_bytes()
    )
    used = await db.bytes_used_for_owner(acc_id)
    if used >= quota:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"storage quota reached ({quota} bytes used); delete something first",
        )


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def request_upload_token(
    request: Request,
    tag: str | None = None,
    video_codec: str | None = None,
    audio_codec: str | None = None,
    format: str | None = None,
    scale: str | None = None,
    poster_scale: str | None = None,
    crf: int | None = None,
    video_preset: str | None = None,
    audio_bitrate: str | None = None,
    keep_animation: bool | None = None,
    preset: str | None = None,
    mode: str | None = None,
    gif_mode: str | None = None,
    remove_audio: bool = False,
    _creds: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict:
    """Шаг 1: проверить права и выдать одноразовый upload-token."""
    cfg: Config = request.app.state.cfg
    vk: valkey.Valkey = request.app.state.vk
    settings: SettingsResolver = request.app.state.settings

    ip = client_ip(request)
    try:
        banned = await ipban.is_banned(vk, ip)
    except VALKEY_ERRORS as exc:
        raise _valkey_unavailable(exc) from None
    if banned:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "temporarily banned")

    if tag is not None and not _TAG_RE.match(tag):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "tag: до 16 символов, только латиница и цифры",
        )

    if video_preset is not None and video_preset not in _VALID_FFMPEG_PRESETS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"недопустимый video_preset: {video_preset}. Допустимы: {', '.join(sorted(_VALID_FFMPEG_PRESETS))}",
        )

    if audio_bitrate is not None and not _VALID_AUDIO_BITRATE_RE.match(audio_bitrate):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"недопустимый audio_bitrate: {audio_bitrate}. Пример: 128k, 192k, 256k",
        )

    if scale is not None and not _VALID_SCALE_RE.match(scale):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"недопустимый scale: {scale}. Допустимы: original, 2160p, 1440p, 1080p, 720p, 480p или WxH",
        )

    if poster_scale is not None and not _VALID_SCALE_RE.match(poster_scale):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"недопустимый poster_scale: {poster_scale}. Допустимы: original, 2160p, 1440p, 1080p, 720p, 480p или WxH",
        )

    acc_id = await authenticate(request)
    perms, _role = await authorize(request, acc_id)

    is_large = has_perm(perms, _PERM_LARGE)
    is_unlimited = has_perm(perms, _PERM_ADMIN_UNLIMITED)
    if is_unlimited:
        max_bytes = _UNLIMITED_BYTES
    elif is_large:
        max_bytes = await settings.max_bytes()
    elif has_perm(perms, _PERM_SMALL):
        max_bytes = await settings.small_max_bytes()
    else:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"недостаточно прав: {_PERM_SMALL}"
        )

    if is_unlimited:
        eff_format = format or ("original" if mode == "original" else "original")
        if gif_mode == "to_webm":
            eff_format = "webm"
        elif gif_mode == "to_static":
            eff_format = "webp"
        elif gif_mode == "keep_gif":
            eff_format = "gif"

        if eff_format in ("gif", "webp"):
            eff_video_codec = "copy"
            eff_audio_codec = "none"
        else:
            eff_video_codec = video_codec or ("copy" if mode == "original" or eff_format == "original" else "libvpx-vp9")
            eff_audio_codec = audio_codec or ("none" if remove_audio else ("copy" if eff_video_codec == "copy" else "libopus"))
        eff_scale = scale or "original"
        eff_poster_scale = poster_scale or "original"
        eff_crf = str(crf) if crf is not None else ""
        eff_video_preset = video_preset or ""
        eff_audio_bitrate = audio_bitrate or ""
        if keep_animation is not None:
            eff_keep_anim = "1" if keep_animation else "0"
        else:
            eff_keep_anim = "0" if (gif_mode == "to_static" or eff_format == "webp") else "1"
        cpu_used = _VIDEO_PRESETS.get(preset or _DEFAULT_PRESET, 5)
    else:
        eff_format = "original"
        eff_video_codec = "copy"
        eff_audio_codec = "copy"
        eff_scale = "original"
        eff_poster_scale = "original"
        eff_crf = ""
        eff_keep_anim = "0"
        eff_video_preset = ""
        eff_audio_bitrate = ""
        cpu_used = _VIDEO_PRESETS["fast"]

    try:
        await _enforce_hourly_limit(request, acc_id, perms)
    except VALKEY_ERRORS as exc:
        raise _valkey_unavailable(exc) from None
    await _enforce_media_count_limit(request, acc_id, perms)
    await _enforce_storage_quota(request, acc_id, perms)

    token = uuid.uuid4().hex
    uptoken_hkey = uptoken_key(token)
    try:
        await vk.hset(
            uptoken_hkey,
            mapping={
                "owner": str(acc_id),
                "tag": tag or "",
                "max_bytes": str(max_bytes),
                "large": "1" if (is_large or is_unlimited) else "0",
                "video_allowed": "1" if (is_large or is_unlimited) else "0",
                "unlimited": "1" if is_unlimited else "0",
                "cpu_used": str(cpu_used),
                "crf": eff_crf,
                "video_codec": eff_video_codec,
                "audio_codec": eff_audio_codec,
                "format": eff_format,
                "scale": eff_scale,
                "poster_scale": eff_poster_scale,
                "video_preset": eff_video_preset,
                "audio_bitrate": eff_audio_bitrate,
                "keep_animation": eff_keep_anim,
            },
        )
        await vk.expire(uptoken_hkey, cfg.upload_token_ttl)
    except VALKEY_ERRORS as exc:
        raise _valkey_unavailable(exc) from None
    return {
        "upload_token": token,
        "expires_in": cfg.upload_token_ttl,
        "upload_url": f"/api/media/upload/{token}",
    }


@router.post(
    "/upload/{upload_token}",
    status_code=status.HTTP_202_ACCEPTED,
    openapi_extra={
        # Тело читается сырым потоком (request.stream()) без File()/UploadFile,
        # чтобы не буферизовать файл целиком и соблюсти лимит размера на лету.
        # Это описание нужно только чтобы Swagger UI показал виджет выбора файла.
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        }
    },
)
async def upload_file(request: Request, upload_token: str) -> dict:
    """Шаг 2: принять файл по одноразовому upload-token."""
    cfg: Config = request.app.state.cfg
    vk: valkey.Valkey = request.app.state.vk
    storage: Storage = request.app.state.storage
    task_log: TaskLog = request.app.state.task_log

    ip = client_ip(request)
    try:
        banned = await ipban.is_banned(vk, ip)
    except VALKEY_ERRORS as exc:
        raise _valkey_unavailable(exc) from None
    if banned:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "temporarily banned")

    bucket = int(time.time()) // 60
    rkey = step2_rate_key(ip, bucket)
    try:
        used = await vk.incr(rkey)
        if used == 1:
            await vk.expire(rkey, 60)
    except VALKEY_ERRORS as exc:
        raise _valkey_unavailable(exc) from None
    if used > _STEP2_RATE_PER_MIN:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "upload rate limit exceeded"
        )

    # Атомарно забрать одноразовый токен (Lua HGETALL + DEL).
    try:
        raw = await vk.eval(_CLAIM_TOKEN_SCRIPT, 1, uptoken_key(upload_token))
    except VALKEY_ERRORS as exc:
        raise _valkey_unavailable(exc) from None
    if not raw:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "upload token not found or expired"
        )

    # Разобрать результат HGETALL (плоский список пар поле-значение).
    payload: dict = {}
    for i in range(0, len(raw), 2):
        k = raw[i].decode() if isinstance(raw[i], bytes) else raw[i]
        v = raw[i + 1].decode() if isinstance(raw[i + 1], bytes) else raw[i + 1]
        payload[k] = v

    owner_id = payload.get("owner")
    tag = payload.get("tag") or ""
    max_bytes = int(payload.get("max_bytes", cfg.small_max_bytes))
    is_large = payload.get("large") == "1"
    video_allowed = payload.get("video_allowed") == "1"
    is_unlimited = payload.get("unlimited") == "1"
    cpu_used = payload.get("cpu_used") or ""
    crf = payload.get("crf") or ""
    video_codec = payload.get("video_codec") or "copy"
    audio_codec = payload.get("audio_codec") or "copy"
    format_choice = payload.get("format") or "original"
    scale = payload.get("scale") or "original"
    poster_scale = payload.get("poster_scale") or "original"
    video_preset = payload.get("video_preset") or ""
    audio_bitrate = payload.get("audio_bitrate") or ""
    keep_animation = payload.get("keep_animation") or "1"

    # Пре-проверка: честно заявленный слишком большой Content-Length → отказ.
    clen = request.headers.get("content-length")
    if clen and clen.isdigit() and int(clen) > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")

    media_token = uuid.uuid4().hex

    # Ранняя валидация типа файла — сигнатура читается ДО записи на диск и до
    # постановки в очередь (см. AUDIT.md §4.1): раньше файл сначала полностью
    # писался на диск и уходил в очередь, реальный тип проверялся только в
    # фоне (worker.py), что позволяло засорять uploads_dir и грузить очередь
    # произвольным содержимым. Здесь же заодно отсекаем video без права
    # video_allowed, не тратя диск/очередь на файл, который всё равно будет
    # отклонён (тот же контроль в worker.py оставлен как defense-in-depth —
    # на случай гонки/повторной постановки задачи).
    header, body = await sniff_and_rewind(request.stream(), SIGNATURE_READ_BYTES)
    sniffed_kind = detect_kind(header)
    if sniffed_kind is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unrecognized file type")
    if sniffed_kind == "video" and not video_allowed:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "video not allowed for this account tier"
        )

    try:
        size = await storage.save_stream(media_token, body, max_bytes)
    except ValueError:
        if is_large:
            # Аккаунт с media.upload.video соврал про Content-Length — не бан,
            # это, скорее всего, свой человек, а не атака: просто отказ.
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "не надо баловаться XD"
            )
        # Реальный объём превысил лимит — заголовок был фейковым → БАН.
        await ipban.ban(vk, ip, cfg.ban_seconds)
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")

    try:
        await vk.hset(
            status_key(media_token),
            mapping={"state": "queued", "owner_id": str(owner_id or "")},
        )
        await vk.expire(status_key(media_token), cfg.status_ttl)
        await vk.xadd(
            cfg.task_stream,
            sign_fields(
                cfg.BUS_SIGNING_KEY,
                inject_carrier(
                    {
                        "op": "convert",
                        "token": media_token,
                        "tag": tag,
                        "owner_id": str(owner_id) if owner_id else "",
                        "backend": cfg.backend,
                        "size": str(size),
                        "video_allowed": "1" if video_allowed else "0",
                        "unlimited": "1" if is_unlimited else "0",
                        "cpu_used": cpu_used,
                        "crf": crf,
                        "video_codec": video_codec,
                        "audio_codec": audio_codec,
                        "format": format_choice,
                        "scale": scale,
                        "poster_scale": poster_scale,
                        "video_preset": video_preset,
                        "audio_bitrate": audio_bitrate,
                        "keep_animation": keep_animation,
                    }
                ),
            ),
            maxlen=cfg.task_stream_maxlen,
            approximate=True,
        )
    except VALKEY_ERRORS as exc:
        storage._safe_unlink(storage.orig_path(media_token))
        raise _valkey_unavailable(exc) from None
    await task_log.record(
        kind="media", op="convert", token_or_cid=media_token, state="queued"
    )
    return {"token": media_token, "status": "queued"}


__all__ = ["router"]
