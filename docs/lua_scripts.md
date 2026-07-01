# Lua-скрипты

Внешние интеграции (выдача услуг и работа с платёжками) исполняются изолированно
в отдельном процессе `luaworker/` через шину Redis Streams. Ядро не «зашивает»
конкретные интеграции: их поведение описывается Lua-скриптами, привязанными к
услугам и платёжным провайдерам.

Каждый скрипт — Lua-модуль, возвращающий таблицу с функцией `handle(ctx)`:

```lua
local M = {}
function M.handle(ctx)
  -- ...
  return { public = {...}, private = {...} }
end
return M
```

- `public` — данные, которые ядро отдаёт клиенту по API;
- `private` — внутренние данные (видит только система).

В песочнице доступны: `json` (encode/decode), `http{ url, method, headers, body }
-> { ok, status, headers, body }`, `string`, `table`, `math`, `os.time/os.date`.

Готовые примеры лежат в `data/lua/` и загружаются как базовые шаблоны при первом
запуске. Управление скриптами — через `POST /api/v1/admin/lua/*` (право `lua.*`).

## Скрипт услуги (`kind = service`)

Управляет жизненным циклом выданной услуги. Ядро вызывает `handle` при выдаче и
при каждом действии ЖЦ, передавая `ctx.action`.

```
ctx = {
  action  = "create" | "renew" | "stop" | "delete" | "freeze",
  user    = {
    id, login, email,
    service = { id, status, state, price, params },  -- конкретная выданная услуга
    payment = <id платежа | nil>,                    -- nil при ручной выдаче
  },
  service = { id, slug, name, price, params, settings, actions },  -- эталон из каталога
}
```

- `user.service.*` — конкретная услуга пользователя (её текущее состояние);
- `service.*` — эталонная услуга из каталога; `service.settings.*` — JSON услуги
  (позволяет одним скриптом обслуживать несколько похожих услуг с разными
  настройками, например разным сроком действия);
- `user.payment` — id платежа, по которому выдана услуга (может быть `nil`, если
  админ выдал вручную без оплаты);
- `service.actions` — список поддерживаемых действий (отдаётся фронтенду).

`handle` возвращает `{ public, private }` и опционально два поля верхнего уровня,
которые подхватывает billing-loop:

- `state` — новое состояние услуги (`active` / `frozen` / `stopped`);
- `expires_at` — unix-время истечения (для планирования истечения услуги).

Базовый шаблон: [`data/lua/base/service_lua.lua`](../data/lua/base/service_lua.lua).
Минимальный пример выдачи: [`data/lua/services/demo_service.lua`](../data/lua/services/demo_service.lua).

## Скрипты платёжного провайдера (`kind = payment`)

Провайдеру соответствуют два скрипта — `init` и `callback`. Подробности потока и
подключения — в [`payments_methods/README.md`](./payments_methods/README.md).

### `init` — инициализация платежа

```
ctx = {
  payment  = { id, amount, currency, target, user_svc_id, return_url },
  provider = { slug, settings = {<секреты>}, extra = {<несекретное>} },
  user     = { id, login, email },
}
```

Возвращает `{ public = { pay_url = ... }, private = { external_id = ... } }`.
Важно прокинуть наш `payment.id` в metadata/payload провайдера, чтобы `callback`
мог найти платёж.

Пример: [`data/lua/payments/demo_init.lua`](../data/lua/payments/demo_init.lua).

### `callback` — обработка вебхука

Ядро принимает **только** server-to-server webhook на статичный URL
`POST /api/v1/callback/payment/{slug}` (страниц success/fail нет). `{slug}` — это
slug платёжной системы, а конкретный платёж скрипт определяет из тела запроса.

```
ctx = {
  provider  = { slug, settings = {<секреты>}, extra = {...} },
  request   = { <тело вебхука и query как есть> },
  directive = "webhook" | "recheck",
}
```

Возвращает `private = { ok, paid, payment_id, external_id, status }`:

- `ok = false` → ядро отвечает `401`;
- `paid = true` → платёж проводится (баланс/выдача услуги) идемпотентно;
- `payment_id` / `external_id` — по ним ядро находит наш платёж.

`directive = "recheck"` означает, что перепроверку инициировало само ядро
(billing-loop или ручной вызов админа): скрипт должен обратиться к API провайдера
за актуальным статусом.

Пример: [`data/lua/payments/demo_callback.lua`](../data/lua/payments/demo_callback.lua).
Боевые шаблоны: `yookassa_*.lua`, `platega_*.lua` в `data/lua/payments/`.
