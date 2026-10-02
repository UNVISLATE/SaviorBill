"""Юнит-тесты защиты секретов при сборке Lua-контекста."""

from __future__ import annotations

import pytest

from lua.context import LuaRunner

pytestmark = pytest.mark.unit


def test_build_ctx_safely_hides_original_exception_text():
    """Сообщение исходного исключения (может содержать секреты) не должно
    попасть в текст пробрасываемой ошибки."""

    secret_value = "sk_live_super_secret_provider_key"

    def _boom(**kwargs):
        raise ValueError(f"validation failed for secret={secret_value}")

    with pytest.raises(RuntimeError) as exc_info:
        LuaRunner._build_ctx_safely("payment", _boom, api_key=secret_value)

    assert secret_value not in str(exc_info.value)
    assert "payment" in str(exc_info.value)


def test_build_ctx_safely_returns_builder_result_on_success():
    def _builder(x):
        return {"ok": x}

    result = LuaRunner._build_ctx_safely("auth", _builder, 42)
    assert result == {"ok": 42}


@pytest.mark.asyncio
async def test_run_includes_resolved_script_version_in_worker_payload():
    class FakeBus:
        def __init__(self) -> None:
            self.calls = []

        async def call(self, kind, payload, metric_label=None):
            self.calls.append((kind, payload, metric_label))
            return {"ok": True}

    bus = FakeBus()
    result = await LuaRunner(bus).run(
        "services/demo/v3.lua",
        "service",
        {"action": "create"},
        slug="demo",
        version=3,
    )

    assert result == {"ok": True}
    assert bus.calls == [
        (
            "run_script",
            {
                "script": "services/demo/v3.lua",
                "kind": "service",
                "ctx": {"action": "create"},
                "script_version": 3,
            },
            "run_script:demo",
        )
    ]
