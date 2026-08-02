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

Во всех классах скриптов в контексте присутствует объект самого шаблона:

- `lua.id` / `lua.slug` / `lua.name` / `lua.kind` — метаданные скрипта;
- `lua.actions` — объявленные действия;
- `lua.settings.*` — **настройки шаблона**: общий JSON, заданный один раз на
  скрипт (`PATCH /api/v1/admin/lua/{id}` полем `settings`) и разделяемый всеми
  услугами/провайдерами, которые используют этот скрипт. Удобно для конфигурации,
  одинаковой у многих услуг (например учётных данных внешней панели), чтобы не
  дублировать её в каждой услуге. Для платежей `lua.settings` не пересекается с
  секретами провайдера — те приходят в `payment.provider_data` (см. ниже).

В песочнице доступны: `json` (encode/decode), `http{ url, method, headers, body }
-> { ok, status, headers, body }`, `string`, `table`, `math`, `os.time/os.date`.

Готовые примеры лежат в `examples/lua/` (услуги, платежи, триггеры). Это
справочные шаблоны — они **не** загружаются автоматически. Чтобы задействовать
скрипт, загрузите его через `POST /api/v1/admin/lua/*` (право `lua.*`); файл
попадёт в рабочую папку `data/lua/<kind>/`, откуда его исполняет luaworker.

## Скрипт услуги (`kind = service`)

Управляет жизненным циклом выданной услуги. Ядро вызывает `handle` при выдаче и
при каждом действии ЖЦ, передавая `ctx.action`.

```
ctx = {
  action  = "create" | "renew" | "stop" | "delete" | "freeze",
  lua     = { id, slug, name, kind, actions, settings },  -- сам шаблон + его настройки
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
- `lua.settings.*` — настройки шаблона, общие для всех услуг этого скрипта
  (например учётные данные панели); услуга может переопределить их через
  `service.settings.*`;
- `user.payment` — id платежа, по которому выдана услуга (может быть `nil`, если
  админ выдал вручную без оплаты);
- `service.actions` — список поддерживаемых действий (отдаётся фронтенду).

`handle` возвращает `{ public, private }` и опционально два поля верхнего уровня,
которые подхватывает billing-loop:

- `state` — новое состояние услуги (`active` / `frozen` / `stopped`);
- `expires_at` — unix-время истечения (для планирования истечения услуги).

Базовый шаблон: [`examples/lua/services/service_lua.lua`](../examples/lua/services/service_lua.lua).
Минимальный пример выдачи: [`examples/lua/services/demo_service.lua`](../examples/lua/services/demo_service.lua).
Боевой пример (VPN через Marzban): [`examples/lua/services/marzban_vpn.lua`](../examples/lua/services/marzban_vpn.lua).

## Скрипты платёжного провайдера (`kind = payment`)

Провайдеру соответствует **один** action-driven скрипт: единое тело
обрабатывает все действия платежа по `ctx.action` (create/callback/check/refund).
Поддерживаемые действия объявляются в `lua_scripts.actions` (create и callback
обязательны). Подробности потока и подключения — в
[`payments_methods/README.md`](payments.md).

Общий контекст:

```
ctx = {
  action  = "create" | "callback" | "check" | "refund",
  lua     = { id, slug, name, kind, actions, settings },
  user    = { id, login, email, ... },
  payment = {
    id, amount, currency, target, user_svc_id, external_id, return_url,
    provider_data = { slug, secrets = {<секреты>}, extra = {<несекретное>} },
  },
  request = { method, ip, headers, query, body },   -- только для action="callback"
}
```

Секреты провайдера приходят в `payment.provider_data.secrets` (шифруются),
иные параметры в `payment.provider_data.extra`.

### `action = "create"` — инициализация платежа

Возвращает `{ public = { pay_url = ... }, private = { external_id = ... } }`.
Важно прокинуть наш `payment.id` в metadata/payload провайдера, чтобы `callback`
мог найти платёж.

### `action = "callback"` — обработка вебхука

Биллинг принимает только webhook на статичный URL
`POST /api/v1/callback/payment/{slug}`. 
`{slug}` — это slug платёжной системы, а конкретный платёж скрипт определяет из тела запроса
(`ctx.request.body`). 
Скрипт сам проверяет подпись/секрет, биллинг полагается на его ответ.

Возвращает `private = { ok, paid, failed, payment_id, external_id, status }`:

- `ok = false` → отвечает `401`;
- `paid = true` → платёж проводится (баланс/выдача услуги) идемпотентно;
- `payment_id` / `external_id` — по ним ядро находит наш платёж.

### `action = "check"` — перепроверка биллингом

Инициируется самим биллингом (billing-loop или ручной вызов админа): скрипт должен
обратиться к API провайдера за актуальным статусом. Возвращает то же, что `callback`.

### `action = "refund"` — возврат средств

Возвращает `private = { ok, refunded, external_id }`.

Пример: [`examples/lua/payments/demo_payment.lua`](../examples/lua/payments/demo_payment.lua).
Рабочие шаблоны: `yookassa_payment.lua`, `platega_payment.lua`.

## Триггерный скрипт (`kind = trigger`)

Связывает доменное событие (`user.registered`, `service.delivered`,
`payment.succeeded` …) с действием-скриптом. Получает
`ctx = { event, config, data, lua }` (`lua.settings.*` — настройки шаблона) и
может, например, отправить уведомление. 
Пример: [`examples/lua/triggers/notify.lua`](../examples/lua/triggers/notify.lua).
