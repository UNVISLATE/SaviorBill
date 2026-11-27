"""Unit-тесты Этапа 2: custom.<action> префикс, allowlist, step-up 2FA/Email и защита от replay/bruteforce."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from schemas.manifest import CustomActionDef, CustomActionVerify, ScriptManifest
from schemas.orders import OrderActionRequest
from schemas.service import ServiceCreate
from services.step_up import request_email_challenge, verify_step_up
from services.twofa import TotpSvc
from security.sec.box import SecBox

pytestmark = pytest.mark.unit


class _FakeValkey:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str):
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and key in self._store:
            return False
        self._store[key] = str(value)
        return True

    async def delete(self, key: str):
        self._store.pop(key, None)

    async def incr(self, key: str) -> int:
        val = int(self._store.get(key, "0")) + 1
        self._store[key] = str(val)
        return val

    async def expire(self, key: str, ttl: int):
        pass


def test_custom_action_prefix_and_duplicates_validation():
    ok = CustomActionDef(key="custom.reboot_vm", label="Перезагрузить")
    assert ok.key == "custom.reboot_vm"
    assert ok.verify == CustomActionVerify.NONE

    with pytest.raises(Exception):
        CustomActionDef(key="reboot", label="Без префикса")

    with pytest.raises(Exception):
        CustomActionDef(key="delete", label="Системное имя")

    manifest = ScriptManifest(
        name="PVE",
        slug="pve",
        custom_actions=[ok],
    )
    assert len(manifest.custom_actions) == 1

    with pytest.raises(ValueError, match="duplicate"):
        ServiceCreate(
            slug="pve-1",
            name="PVE",
            settings={"custom_actions": [ok.model_dump(), ok.model_dump()]},
        )


def test_order_action_request_accepts_long_custom_action():
    req = OrderActionRequest(action="custom.reinstall_operating_system", verify_code="123456")
    assert req.action == "custom.reinstall_operating_system"


@pytest.mark.asyncio
async def test_step_up_email_challenge_binding_and_one_time_use():
    vk = _FakeValkey()
    sent_bodies: list[str] = []

    class _Mail:
        async def send_raw(self, *, to: str, subject: str, body: str):
            sent_bodies.append(body)

    acc = SimpleNamespace(id=11, email="u@example.com", totp_enabled=False, totp_secret=None)
    ttl = await request_email_challenge(vk, _Mail(), acc, 100, "custom.reinstall_os")
    assert ttl == 300
    assert len(sent_bodies) == 1

    # Извлекаем 6-значный код из письма
    code = sent_bodies[0].split(": ")[1].split("\n")[0].strip()

    # Cross-action replay: код от custom.reinstall_os НЕ подходит для custom.reboot
    with pytest.raises(HTTPException) as exc_cross:
        await verify_step_up(vk, None, acc, 100, "custom.reboot", "email", code)
    assert exc_cross.value.status_code == 403

    # Правильный action: проходит и удаляется (одноразовый)
    await verify_step_up(vk, None, acc, 100, "custom.reinstall_os", "email", code)

    # Повторное использование того же кода запрещено
    with pytest.raises(HTTPException) as exc_replay:
        await verify_step_up(vk, None, acc, 100, "custom.reinstall_os", "email", code)
    assert exc_replay.value.status_code == 403


@pytest.mark.asyncio
async def test_step_up_totp_replay_and_bruteforce_guard():
    import pyotp
    from cryptography.fernet import Fernet

    vk = _FakeValkey()
    box = SecBox(Fernet.generate_key().decode())
    totp = TotpSvc(box)
    acc = SimpleNamespace(id=22, login="u22", email="u22@example.com", totp_enabled=False, totp_secret=None, totp_recovery=[])
    secret, _ = totp.start_enrollment(acc)
    code = pyotp.TOTP(secret).now()
    totp.enable(acc, code)

    # Первый раз в текущем окне проходит
    await verify_step_up(vk, box, acc, 50, "custom.wipe", "2fa", code)

    # Повторный вызов с тем же TOTP в том же окне -> 409 Conflict
    with pytest.raises(HTTPException) as exc_rep:
        await verify_step_up(vk, box, acc, 50, "custom.wipe", "2fa", code)
    assert exc_rep.value.status_code == 409

    # Брутфорс 5 неверных кодов -> 429
    for _ in range(5):
        with pytest.raises(HTTPException) as exc_bad:
            await verify_step_up(vk, box, acc, 51, "custom.wipe", "2fa", "000000")
        assert exc_bad.value.status_code == 403

    with pytest.raises(HTTPException) as exc_429:
        await verify_step_up(vk, box, acc, 51, "custom.wipe", "2fa", "000000")
    assert exc_429.value.status_code == 429
