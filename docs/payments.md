# Платёжные провайдеры

Биллинг не «зашивает» конкретные платёжки в код: каждая платёжная система
описывается записью в таблице `pay_providers` и **одним** action-driven
Lua-скриптом, который изолирует её особенности. Это позволяет добавлять
провайдеров без изменения ядра.

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
   `amount` в теле запроса принимается **только для `target=balance`**
   (произвольная сумма пополнения). Для `target=service` поле `amount`
   запрещено (422, если передано) — сумма всегда берётся из
   `service.price` на сервере, чтобы клиент не мог создать платёж за
   услугу на произвольно малую сумму и получить её после подтверждения
   этой суммы провайдером.
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

```
ctx.action  = "create" | "callback" | "check" | "refund"
ctx.user    = { id, login, email, ... }
ctx.payment = {
  id, amount, currency, target, user_svc_id, external_id, return_url,
  provider_data = { slug, secrets = {<секреты>}, extra = {<несекретное>}, currency },
}
ctx.request = { method, ip, headers, query, body }   -- только для action="callback"
```

Возврат `{ public = {...}, private = {...} }`:

- `create`   → `public.pay_url`, `private.external_id`;
- `callback` → `private.ok`, `private.paid`|`failed`, `private.payment_id` | `external_id`;
- `check`    → `private.ok`, `private.paid`|`failed`, `private.external_id`;
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

Конкретные значения `secrets`/`extra` — в файлах:

- [`yookassa.md`](payments_methods/yookassa.md)
- [`platega.md`](payments_methods/platega.md)

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

