"""Юнит-тесты защиты секретов при сборке Lua-контекста (AUDIT.md M3)."""

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
