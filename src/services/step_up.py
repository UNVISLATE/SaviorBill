"""Сервис step-up подтверждения (2FA / Email-код) для критичных действий услуг."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time

import valkey.asyncio as valkey
from fastapi import HTTPException, status

from lifecycle.notifications import EmailSender
from models.user import UserModel
from schemas.manifest import CustomActionVerify
from security.sec.box import SecBox
from services.audit import audit
from services.twofa import TotpSvc

_CHALLENGE_TTL_SEC = 300
_COOLDOWN_TTL_SEC = 60
_MAX_FAIL_ATTEMPTS = 5


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def _challenge_key(acc_id: int, usvc_id: int, action_key: str) -> str:
    return f"stepup:email:{acc_id}:{usvc_id}:{action_key}"


def _cooldown_key(acc_id: int, usvc_id: int, action_key: str) -> str:
    return f"stepup:email:cd:{acc_id}:{usvc_id}:{action_key}"


def _fail_key(acc_id: int, usvc_id: int, action_key: str) -> str:
    return f"stepup:fail:{acc_id}:{usvc_id}:{action_key}"


async def request_email_challenge(
    vk: valkey.Valkey,
    mail: EmailSender,
    acc: UserModel,
    usvc_id: int,
    action_key: str,
) -> int:
    """Отправить одноразовый 6-значный код подтверждения на email пользователя."""
    if not acc.email:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "account email is not configured for verification",
        )
    cd_key = _cooldown_key(acc.id, usvc_id, action_key)
    if await vk.get(cd_key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "verification code was sent recently, please wait",
        )

    code = f"{secrets.randbelow(1_000_000):06d}"
    payload = json.dumps({"code_hash": _hash_code(code)})
    await vk.set(_challenge_key(acc.id, usvc_id, action_key), payload, ex=_CHALLENGE_TTL_SEC)
    await vk.set(cd_key, "1", ex=_COOLDOWN_TTL_SEC)
    await vk.delete(_fail_key(acc.id, usvc_id, action_key))

    await mail.send_raw(
        to=acc.email,
        subject=f"Код подтверждения действия: {action_key}",
        body=(
            f"Код подтверждения для действия {action_key} (услуга #{usvc_id}): {code}\n"
            f"Код действителен 5 минут. Если это были не вы, немедленно смените пароль."
        ),
    )
    return _CHALLENGE_TTL_SEC


async def verify_step_up(
    vk: valkey.Valkey,
    box: SecBox,
    acc: UserModel,
    usvc_id: int,
    action_key: str,
    required_verify: str,
    code: str | None,
) -> None:
    """Проверить step-up подтверждение (2fa / email / 2fa_or_email)."""
    if not required_verify or required_verify == CustomActionVerify.NONE:
        return

    if required_verify == CustomActionVerify.TWOFA and not acc.totp_enabled:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "error": "totp_not_enabled",
                "verify_required": CustomActionVerify.TWOFA,
                "message": "2FA must be enabled to perform this action",
            },
        )
    if required_verify == CustomActionVerify.EMAIL and not acc.email:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "account email is required to perform this action",
        )

    effective_mode = required_verify
    if required_verify == CustomActionVerify.TWOFA_OR_EMAIL and not acc.totp_enabled:
        effective_mode = CustomActionVerify.EMAIL

    if not code or not code.strip():
        raise HTTPException(
            status.HTTP_428_PRECONDITION_REQUIRED,
            detail={
                "error": "verification_required",
                "verify_required": effective_mode,
                "totp_enabled": bool(acc.totp_enabled),
                "challenge_ttl": _CHALLENGE_TTL_SEC,
            },
        )

    f_key = _fail_key(acc.id, usvc_id, action_key)
    fails_raw = await vk.get(f_key)
    if fails_raw and int(fails_raw) >= _MAX_FAIL_ATTEMPTS:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many failed verification attempts, please try again later",
        )

    clean_code = code.strip().replace(" ", "")
    verified = False

    # 1. Проверка TOTP (строго без recovery-кодов + защита от replay в 30-сек окне).
    if required_verify in (CustomActionVerify.TWOFA, CustomActionVerify.TWOFA_OR_EMAIL) and acc.totp_enabled:
        if TotpSvc(box).verify_code(acc, clean_code):
            time_step = int(time.time() // 30)
            replay_key = f"stepup:totp_used:{acc.id}:{time_step}"
            # SET NX EX 60: разрешаем конкретный TOTP-токен только один раз за шаг
            acquired = await vk.set(replay_key, "1", ex=60, nx=True)
            if not acquired:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "2FA code already used, wait for the next code",
                )
            verified = True

    # 2. Проверка одноразового Email-кода, привязанного к (acc_id, usvc_id, action_key).
    if not verified and required_verify in (CustomActionVerify.EMAIL, CustomActionVerify.TWOFA_OR_EMAIL):
        c_key = _challenge_key(acc.id, usvc_id, action_key)
        raw_ch = await vk.get(c_key)
        if raw_ch:
            try:
                data = json.loads(raw_ch)
                expected_hash = str(data.get("code_hash") or "")
            except Exception:
                expected_hash = ""
            if expected_hash and hmac.compare_digest(_hash_code(clean_code), expected_hash):
                await vk.delete(c_key)
                verified = True

    if not verified:
        n = await vk.incr(f_key)
        if n == 1:
            await vk.expire(f_key, _CHALLENGE_TTL_SEC)
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "error": "invalid_verification_code",
                "verify_required": effective_mode,
                "message": "invalid or expired verification code",
            },
        )

    await vk.delete(f_key)


__all__ = ["request_email_challenge", "verify_step_up"]
