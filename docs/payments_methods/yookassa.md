# ЮKassa (YooKassa)

Официальная документация: <https://yookassa.ru/developers>. Сценарий —
**Redirect** (одностадийный платёж, `capture=true`).

Скрипт: `data/lua/payments/yookassa_payment.lua` (единый, action-driven:
create/callback/check/refund).

## Что заполнить

### `secrets` (шифруется, попадает в `payment.provider_data.secrets`)

| Поле | Обяз. | Описание |
|------|-------|----------|
| `shop_id` | да | Идентификатор магазина (shopId) из ЛК ЮKassa |
| `secret_key` | да | Секретный ключ API из ЛК ЮKassa |
| `return_url` | нет | URL возврата по умолчанию (если клиент не передал свой) |

### `extra` (несекретное, `payment.provider_data.extra`)

Не требуется.

### Пример создания провайдера

```http
POST /api/v1/admin/purchases/providers
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "slug": "yookassa",
  "title": "ЮKassa",
  "enabled": true,
  "currency": "RUB",
  "secrets": {
    "shop_id": "123456",
    "secret_key": "live_xxxxxxxxxxxxxxxxxxxxxx",
    "return_url": "https://shop.example.com/pay/return"
  },
  "script_id": 10
}
```

## Как это работает

**Инициализация** (`action=create`): скрипт шлёт
`POST https://api.yookassa.ru/v3/payments` с Basic-авторизацией
`base64(shop_id:secret_key)`, заголовком `Idempotence-Key` и телом:

```json
{
  "amount": { "value": "100.00", "currency": "RUB" },
  "capture": true,
  "confirmation": { "type": "redirect", "return_url": "..." },
  "description": "Payment #<id>",
  "metadata": { "payment_id": "<наш id>" }
}
```

Из ответа берётся `confirmation.confirmation_url` → отдаётся клиенту как
`pay_url`, а `id` платежа сохраняется как `external_id`.

**Колбэк** (`action=callback`): в ЛК ЮKassa нужно настроить уведомление
`payment.succeeded` на URL:

```
https://<PUBLIC_URL>/api/v1/callback/payment/yookassa
```

Скрипт берёт `object.id` из тела уведомления (`ctx.request.body`) и
**перепроверяет** статус запросом `GET https://api.yookassa.ru/v3/payments/{id}`.
Платёж считается успешным при `status == "succeeded"`. Наш внутренний
`payment_id` восстанавливается из `metadata.payment_id`. Действие
`action=check` использует тот же запрос статуса (перепроверка ядром), а
`action=refund` шлёт `POST https://api.yookassa.ru/v3/refunds`.

## Проверка

1. Создать платёж: `POST /api/v1/user/purchases/create` с
   `{ "amount": 10, "provider": "yookassa", "target": "balance" }`.
2. Перейти по `public_data.pay_url`, оплатить тестовой картой ЮKassa.
3. Дождаться вебхука (или сымитировать: `POST .../callback/payment/yookassa`
   с телом `{"event":"payment.succeeded","object":{"id":"<id из ЮKassa>"}}`) —
   баланс пополнится, статус платежа станет `paid`.
