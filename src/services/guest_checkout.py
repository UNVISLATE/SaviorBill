"""Сервис гостевого чекаута, токенов просмотра заказов и клейма аккаунтов."""

from __future__ import annotations

import hmac
import json
from typing import Any

from fastapi import HTTPException, status
import valkey.asyncio as valkey
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.settings import SystemSettingsMngr
from enums import BaseRole
from lifecycle.notifications import EmailEvent, EmailSender
from models.user import UserModel, UserMngr
from schemas.types import normalize_email
from security.sec.crypt import generate_base_token, generate_numeric_code
from security.sec.pwd import hash_pass

_ORDER_TOKEN_PREFIX = "guest:order_token:"
_CLAIM_PREFIX = "guest:claim:"
_CLAIM_CODE_PREFIX = "guest:claim:code:"
_CLAIM_FAIL_PREFIX = "guest:claim:fail:"
_CLAIM_MAX_FAILS = 5
_CODE_DIGITS = 6


def mask_email(email: str) -> str:
    """Маскирование email адреса для публичного отображения (ivan@gmail.com -> i***n@gmail.com)."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "***"
    else:
        masked_local = local[0] + "***" + local[-1]
    return f"{masked_local}@{domain}"


class GuestCheckoutSvc:
    """Бизнес-логика гостевых покупок, временных токенов и клейма аккаунтов."""

    def __init__(
        self,
        session: AsyncSession,
        vk: valkey.Valkey,
        sender: EmailSender,
        settings: SystemSettingsMngr,
    ) -> None:
        self.s = session
        self.vk = vk
        self.sender = sender
        self.settings = settings

    async def create_order_view_token(
        self,
        order_id: int,
        payment_id: int,
        account_id: int,
        requires_auth: bool = False,
    ) -> str:
        """Создать защищённый временный токен для просмотра заказа покупателем."""
        ttl = await self.settings.get_int("shop.guest.order_token_ttl", 86400)
        token = generate_base_token()
        payload = {
            "order_id": order_id,
            "payment_id": payment_id,
            "account_id": account_id,
            "requires_auth": requires_auth,
        }
        await self.vk.set(_ORDER_TOKEN_PREFIX + token, json.dumps(payload), ex=ttl)
        return token

    async def get_order_token_payload(self, token: str) -> dict[str, Any] | None:
        """Получить сохранённую нагрузку токена просмотра заказа."""
        raw = await self.vk.get(_ORDER_TOKEN_PREFIX + token)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def request_guest_claim(self, email: str) -> tuple[str, int]:
        """Запросить 6-значный OTP-код для подтверждения гостевого аккаунта.

        :return: (claim_token, ttl_seconds)
        """
        norm = normalize_email(email)
        if not norm:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "invalid email address"
            )
        user_mngr = UserMngr(self.s)
        acc = await user_mngr.by_email(norm)
        if not acc or not acc.role or acc.role.key != BaseRole.GUEST:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "guest account with this email not found or already verified",
            )

        ttl = await self.settings.get_int("shop.guest.claim_code_ttl", 600)
        claim_token = generate_base_token()
        code = generate_numeric_code(_CODE_DIGITS)
        payload = {"account_id": acc.id, "email": acc.email}

        await self.vk.set(_CLAIM_PREFIX + claim_token, json.dumps(payload), ex=ttl)
        await self.vk.set(_CLAIM_CODE_PREFIX + claim_token, code, ex=ttl)

        ctx = {
            "user": {"id": acc.id, "login": acc.login, "email": acc.email},
            "code": code,
            "ttl_minutes": max(1, ttl // 60),
        }
        sent = await self.sender.send_template(
            EmailEvent.GUEST_CLAIM_CONFIRM, acc.email, ctx
        )
        if not sent:
            await self.sender.mail.send(
                acc.email,
                "Confirm your account registration",
                f"Your SaviorBill confirmation code: {code}",
            )
        return claim_token, ttl

    async def verify_guest_claim(
        self, claim_token: str, code: str, password: str
    ) -> UserModel:
        """Проверить OTP-код, задать пароль и повысить роль гостя до user."""
        raw = await self.vk.get(_CLAIM_PREFIX + claim_token)
        if not raw:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "claim session not found or expired"
            )

        stored_code = await self.vk.get(_CLAIM_CODE_PREFIX + claim_token)
        if stored_code is None or not hmac.compare_digest(stored_code, code.strip()):
            fails = await self.vk.incr(_CLAIM_FAIL_PREFIX + claim_token)
            if fails == 1:
                await self.vk.expire(_CLAIM_FAIL_PREFIX + claim_token, 600)
            if fails >= _CLAIM_MAX_FAILS:
                await self.vk.delete(
                    _CLAIM_PREFIX + claim_token,
                    _CLAIM_CODE_PREFIX + claim_token,
                    _CLAIM_FAIL_PREFIX + claim_token,
                )
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid confirmation code")

        payload = json.loads(raw)
        acc = await self.s.get(UserModel, payload["account_id"])
        if not acc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")

        user_mngr = UserMngr(self.s)
        user_role = await user_mngr.role_by_key(BaseRole.USER)
        if user_role:
            acc.role_id = user_role.id
            acc.role = user_role

        acc.pass_hash = hash_pass(password)
        await self.vk.delete(
            _CLAIM_PREFIX + claim_token,
            _CLAIM_CODE_PREFIX + claim_token,
            _CLAIM_FAIL_PREFIX + claim_token,
        )
        await self.s.flush()
        return acc
