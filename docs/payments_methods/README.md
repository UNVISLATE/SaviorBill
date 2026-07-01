# Платёжные провайдеры

Биллинг не «зашивает» конкретные платёжки в код: каждая платёжная система
описывается записью в таблице `pay_providers` и двумя Lua-скриптами, которые
изолируют её особенности. Это позволяет добавлять провайдеров без изменения
ядра.

## Архитектура

Платёж проходит два этапа, каждому соответствует свой скрипт:

| Этап | Скрипт | Что делает |
|------|--------|------------|
| Инициализация | `init` | Создаёт платёж у провайдера, возвращает ссылку оплаты (`public.pay_url`) и `external_id` транзакции |
| Колбэк (webhook) | `callback` | Принимает серверный вебхук провайдера, **перепроверяет** статус у провайдера и сообщает результат |

Поток данных:

1. `POST /api/v1/user/purchases/create` → ядро создаёт `UserPayment` (статус
   `pending`) и запускает **init**-скрипт. Клиент получает `public_data.pay_url`.
2. Пользователь оплачивает на стороне провайдера.
3. Провайдер дёргает `POST /api/v1/callback/payment/{slug}` (только server-to-server
   webhook; страниц success/fail ядро не обслуживает) → ядро запускает
   **callback**-скрипт. Тот возвращает `private = { ok, paid, payment_id,
   external_id, status }`.
4. Если `ok=false` → ядро отвечает `401`. Если `paid=true` → платёж проводится
   (баланс/выдача услуги) идемпотентно.

> **Директива `recheck`.** Долгие `pending`-платежи планировщик (billing-loop)
> сам ставит на перепроверку: callback-скрипт вызывается с
> `ctx.request.directive = "recheck"` и обращается к API провайдера. После
> `BILLING_PAY_RECHECK_MAX` безрезультатных попыток платёж переводится в статус
> `wait` (авто-перепроверки прекращаются). Ручной повтор —
> `POST /api/v1/admin/purchases/{id}/recheck` (право `purchases.recheck`).

### Контракт скриптов

`init` получает `ctx`:

```
ctx.payment  = { id, amount, currency, target, user_svc_id, return_url }
ctx.provider = { slug, settings = {<секреты>}, extra = {<несекретное>} }
ctx.user     = { id, login, email }
```

и обязан вернуть `{ public = { pay_url = ... }, private = { external_id = ... } }`.

`callback` получает `ctx`:

```
ctx.provider  = { slug, settings = {<секреты>}, extra = {...} }
ctx.request   = { <тело вебхука и query как есть> }
ctx.directive = "webhook" | "recheck"
```

и обязан вернуть `{ private = { ok, paid, payment_id, external_id, status } }`.

> **Безопасность.** Готовые шаблоны не доверяют телу вебхука: они **повторно
> запрашивают статус** платежа у провайдера по его API (server-to-server) с
> мерчант-секретами. Это надёжнее проверки подписи и устойчиво к подделке
> уведомления.

В Lua-песочнице доступны: `json` (encode/decode), `http{ url, method, headers,
body } -> { ok, status, headers, body }`, `string`, `table`, `math`,
`os.time/os.date`.

## Как подключить провайдера

1. **Загрузить скрипты** через `POST /api/v1/admin/lua/*` (право `lua.*`),
   `kind=payment`. Запомнить выданные `id` init- и callback-скриптов.
2. **Создать провайдера** `POST /api/v1/admin/purchases/providers`
   (право `purchases.providers`):

   ```json
   {
     "slug": "yookassa",
     "title": "ЮKassa",
     "enabled": true,
     "currency": "RUB",
     "secrets": { "...": "..." },
     "extra": { "...": "..." },
     "init_script_id": 10,
     "cb_script_id": 11
   }
   ```

   - `secrets` — шифруется (SecBox) и попадает в скрипт как `provider.settings`.
   - `extra` — несекретные параметры, попадает как `provider.extra`.
3. **Указать в ЛК провайдера** URL вебхука:
   `https://<PUBLIC_URL>/api/v1/callback/payment/<slug>`.

Конкретные значения `secrets`/`extra` — в файлах:

- [`yookassa.md`](./yookassa.md)
- [`platega.md`](./platega.md)

Готовые тела скриптов лежат в `data/lua/payments/`:
`yookassa_init.lua`, `yookassa_callback.lua`, `platega_init.lua`,
`platega_callback.lua`.
