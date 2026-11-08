# Платёжные провайдеры

Биллинг не «зашивает» конкретные платёжки в код: каждая платёжная система
описывается записью в таблице `pay_providers` и **одним** action-driven
Lua-скриптом, который изолирует её особенности. Это позволяет добавлять
провайдеров без изменения ядра.

Полный общий контракт Lua-скриптов находится в
[`docs/lua/scripts.md`](lua/scripts.md), а краткая инструкция для ИИ — в
[`docs/lua/llms.txt`](lua/llms.txt).

## Архитектура

У провайдера один скрипт, обрабатывающий все действия платежа по `ctx.action`:

| Действие (`action`) | Что делает |
|---------------------|------------|
| `create`   | Создаёт платёж у провайдера, возвращает ссылку оплаты (`public.pay_url`) и `external_id` транзакции |
| `callback` | Принимает серверный вебхук провайдера, проверяет его и сообщает результат (доверенный канал) |
| `check`    | Перепроверка статуса ядром (billing-loop / ручной recheck) запросом к API провайдера |
| `refund`   | Возврат средств по платежу |

Скрипт объявляет поддерживаемые действия в `lua_scripts.actions`. Обязательны
`create` и `callback`; `check` и `refund` — опциональны.

Поток данных:

1. `POST /api/v1/user/purchases/create` → ядро создаёт `UserPayment` (статус
   `pending`) и запускает скрипт с `action=create`. Клиент получает
   `public_data.pay_url`.
   Сумма платежа определяется строго сервером:
   - Для `target=balance` (пополнение баланса): `amount` задаётся клиентом (произвольная сумма > 0 в базовой валюте).
   - Для `target=service` (покупка услуги): прямое поле `amount` запрещено схемой `PaymentCreate` (422/ValidationError). Авторитетный расчёт стоимости, длительности и эффективных настроек выполняется сервером (`services.pricing.resolve_service_order`) на основе модели услуги (`price_type`: `fixed`, `custom`, `tiered`, `configurable`), параметров заказа (`custom_amount`, `tier_code`, `components`, `form`) и скидки по промокоду. Клиент не может навязать произвольную сумму в обход серверной валидации схемы ценообразования.
2. Пользователь оплачивает на стороне провайдера.
3. Провайдер дёргает `POST /api/v1/callback/payment/{slug}` (только
   server-to-server webhook; страниц success/fail ядро не обслуживает) → ядро
   запускает скрипт с `action=callback`. Тот возвращает
   `private = { ok, paid, failed, payment_id, external_id }`.
4. Если `ok=false` → ядро отвечает `401`. Если `paid=true` → платёж проводится
   (баланс/выдача услуги) идемпотентно.

> **Доверие вебхуку.** Колбэк — доверенный канал: скрипт сам проверяет
> подпись/секрет (или перепроверяет статус у API), а ядро полагается на его
> ответ. Инициируемая ядром перепроверка выполняется отдельным действием
> `check`.

> **Действие `check`.** Долгие `pending`-платежи планировщик (billing-loop) сам
> ставит на перепроверку: скрипт вызывается с `action=check` и обращается к API
> провайдера. После `BILLING_PAY_RECHECK_MAX` безрезультатных попыток платёж
> переводится в статус `wait` (авто-перепроверки прекращаются). Ручной повтор —
> `POST /api/v1/admin/purchases/{id}/recheck` (право `purchases.recheck`).
> Возврат — `POST /api/v1/admin/purchases/{id}/refund` (право `purchases.refund`).

### Контракт скрипта

Скрипт получает `ctx`:

```lua
ctx.action  = "create" | "callback" | "check" | "refund"
ctx.user    = { id, login, email, ... }
ctx.payment = {
  id,
  amount,        -- рассчитанная сумма в валюте провайдера (например "950.00")
  currency,      -- валюта провайдера (например "RUB")
  base_amount,   -- сумма в базовой валюте инстанса (например "10.00")
  base_currency, -- базовая валюта инстанса (например "USD")
  fx_rate,       -- зафиксированный курс обмена на момент создания счёта
  target, user_svc_id, external_id, return_url,
  provider_data = {
    slug, currency,
    currencies = { "RUB", "USD", ... },
    secrets = {<секреты>},
    extra = {<несекретное>}
  },
}
ctx.request = { method, ip, headers, query, body }   -- только для action="callback"
```

> **Курсы валют и обратная конвертация (Rate Lock):**
> 1. В `action=create` ядро биллинга конвертирует сумму заказа/пополнения из базовой
>    валюты инстанса в валюту провайдера и фиксирует курс (`payment.fx_rate`).
> 2. В `action=callback` и `action=check` скрипт сообщает подтверждённую сумму и валюту:
>    `private = { ok = true, paid = true, paid_amount = "950.00", paid_currency = "RUB", ... }`.
> 3. Ядро биллинга выполняет обратную конвертацию оплаченной суммы в базовую валюту
>    инстанса по зафиксированному курсу счёта.

Возврат `{ public = {...}, private = {...} }`:

- `create`   → `public.pay_url`, `private.external_id`;
- `callback` → `private.ok`, `private.paid`|`failed`, `private.paid_amount`, `private.paid_currency`, `private.payment_id` | `external_id`;
- `check`    → `private.ok`, `private.paid`|`failed`, `private.paid_amount`, `private.paid_currency`, `private.external_id`;
- `refund`   → `private.ok`, `private.refunded`.

> **Безопасность.** Готовые шаблоны ЮKassa/Platega не доверяют телу вебхука: они
> **повторно запрашивают статус** платежа у провайдера по его API
> (server-to-server) с мерчант-секретами. Это надёжнее проверки подписи и
> устойчиво к подделке уведомления.

В Lua-песочнице доступны: `json` (encode/decode), `http{ url, method, headers,
body } -> { ok, status, headers, body }`, `string`, `table`, `math`,
`os.time/os.date`.

## Как подключить провайдера

1. **Загрузить скрипт** через `POST /api/v1/admin/lua/*` (право `lua.*`),
   `kind=payment`, `actions=["create","callback","check","refund"]`. Запомнить
   выданный `id` скрипта.
2. **Создать провайдера** `POST /api/v1/admin/purchases/providers`
   (право `purchases.providers.create`):

   ```json
   {
     "slug": "yookassa",
     "title": "ЮKassa",
     "enabled": true,
     "currency": "RUB",
     "secrets": { "...": "..." },
     "extra": { "...": "..." },
     "script_id": 10
   }
   ```

   - `secrets` — шифруется (SecBox) и попадает в скрипт как
     `payment.provider_data.secrets`.
   - `extra` — несекретные параметры, попадает как `payment.provider_data.extra`.
3. **Указать в ЛК провайдера** URL вебхука:
   `https://<PUBLIC_URL>/api/v1/callback/payment/<slug>`.

Готовые тела скриптов лежат в `examples/lua/payments/`:
`yookassa_payment.lua`, `platega_payment.lua` (и `demo_payment.lua` для тестов).

## Скидочные промокоды (kind=discount)

`POST /api/v1/user/services/create` и `POST /api/v1/user/purchases/create`
принимают опциональный `promocode` (второй — только для `target=service`).
Код должен быть каталога `kind=discount`; для `kind=bonus`/`kind=service`
используется отдельный `POST /api/v1/promocodes/redeem`.

- **Оплата с баланса** (`services/create`): скидка применяется и код
  погашается сразу же (в той же транзакции, что и списание/выдача) — платёж
  либо целиком проходит, либо целиком откатывается.
- **Оплата через провайдера** (`purchases/create`): скидка уменьшает
  `amount` платежа немедленно, но погашение кода (запись в
  `promocode_use`, инкремент `used_count`) откладывается до подтверждённой
  оплаты — в `PayMngr._settle`, вызываемого из `action=callback`/`check`.
  Если платёж так и не будет оплачен, код остаётся непотраченным. Между
  созданием платежа и подтверждением оплаты промокод хранится в
  `user_services.private_data.promocode_id` — временная связка, не
  отдельная колонка.

**Предпоказ скидки** (не мутирует состояние, ничего не резервирует):

- `GET /api/v1/promocodes/{code}/quote?service_id=<id>` — отдельный
  эндпойнт;
- `GET /api/v1/catalog/services/{id}?promo=<code>` — тот же расчёт как
  дополнительное поле `promo_quote` в ответе о услуге.

Оба варианта работают без авторизации, но без аккаунта не проверяются
лимиты "на пользователя" (`per_user`, повторное использование того же
кода) — только общая валидность кода (активен/не просрочен/лимит
активаций/`kind=discount`). С Bearer-токеном проверяются оба уровня.
