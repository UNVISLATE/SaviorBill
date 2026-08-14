"""Юнит-тест атомарного гашения OAuth `state` (AUDIT.md §2.2).

Раньше `state` читался GET-ом отдельно от DELETE — два параллельных callback
с одним и тем же `state` могли оба пройти проверку одноразовости (race
condition). Теперь используется `GETDEL`, тот же паттерн, что и в
`dependencies/password.py`.
"""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from dependencies.oauth import OAuthSvc

pytestmark = pytest.mark.unit


class _FakeValkey:
    """Мини in-memory Valkey с атомарным GETDEL."""

    def __init__(self) -> None:
        self._vals: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._vals[key] = value

    async def get(self, key: str) -> str | None:
        return self._vals.get(key)

    async def getdel(self, key: str) -> str | None:
        return self._vals.pop(key, None)

    async def delete(self, key: str) -> None:
        self._vals.pop(key, None)


def _svc(vk) -> OAuthSvc:
    return OAuthSvc(
        session=None,
        vk=vk,
        bus=None,
        cfg=None,
        box=None,
        sender=None,
        settings=None,
    )


@pytest.mark.asyncio
async def test_pop_state_consumes_key_once():
    vk = _FakeValkey()
    await vk.set("oauth:state:tok1", json.dumps({"slug": "google", "account_id": None, "nonce": "n"}))
    svc = _svc(vk)

    payload = await svc._pop_state("google", "tok1")
    assert payload["nonce"] == "n"

    # Второй запрос с тем же state — ключ уже погашен первым (атомарно).
    with pytest.raises(HTTPException) as exc:
        await svc._pop_state("google", "tok1")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_pop_state_rejects_slug_mismatch():
    vk = _FakeValkey()
    await vk.set("oauth:state:tok2", json.dumps({"slug": "github", "account_id": None, "nonce": "n"}))
    svc = _svc(vk)

    with pytest.raises(HTTPException) as exc:
        await svc._pop_state("google", "tok2")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_pop_state_rejects_unknown_state():
    svc = _svc(_FakeValkey())
    with pytest.raises(HTTPException) as exc:
        await svc._pop_state("google", "missing")
    assert exc.value.status_code == 400
