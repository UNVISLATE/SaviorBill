# Lua-документация

Документы в этой папке описывают контракт Lua-интеграций SaviorBill.

- [`scripts.md`](scripts.md) — общий контракт `handle(ctx)`, service/payment/
  trigger scripts и структура контекста.
- [`fx.md`](fx.md) — Lua-источник курсов валют.
- [`llms.txt`](llms.txt) — краткая инструкция для ИИ: как писать и проверять
  скрипты без выдумывания полей или API.

Runtime LuaWorker описан в [`luaworker/README.md`](../../luaworker/README.md).
Платёжный поток и HTTP API описаны в [`docs/payments.md`](../payments.md).
Сквозная подпись сообщений и Lua-аспекты безопасности описаны в
[`docs/security.md`](../security.md), метрики — в
[`docs/telemetry.md`](../telemetry.md).

При изменении Lua-контракта сначала обновляются `scripts.md` и `llms.txt`,
затем примеры в `examples/lua/` и тестовые скрипты в `tests/data/lua/`.
