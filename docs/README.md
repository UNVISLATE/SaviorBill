# Документация SaviorBill

Документы сгруппированы по подсистемам и по уровню детализации.

## Подсистемы

- [`payments.md`](payments.md) — платёжный поток, провайдеры и callback API.
- [`media.md`](media.md) — загрузка и обработка медиафайлов.
- [`security.md`](security.md) — границы доверия, подписи, SSRF и секреты.
- [`telemetry.md`](telemetry.md) — логи, метрики и трассировка.
- [`lua/`](lua/README.md) — Lua-контракт, LuaWorker и инструкции для ИИ.

## Источники истины

- Контракт API и модели — код рядом с соответствующей подсистемой.
- Lua script contract — [`lua/scripts.md`](lua/scripts.md).
- LuaWorker runtime — [`../luaworker/README.md`](../luaworker/README.md).
- Краткие правила для генерации Lua — [`lua/llms.txt`](lua/llms.txt).

Если документ противоречит коду, сначала проверить актуальный runtime и схемы,
затем исправить документ и связанные примеры/тесты в одной задаче.
