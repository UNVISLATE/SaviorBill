# ЮKassa (YooKassa)

Официальная документация: <https://yookassa.ru/developers>. Сценарий —
**Redirect** (одностадийный платёж, `capture=true`).

Скрипты: `data/lua/payments/yookassa_init.lua`,
`data/lua/payments/yookassa_callback.lua`.

## Что заполнить

### `secrets` (шифруется, попадает в `provider.settings`)

| Поле | Обяз. | Описание |
|------|-------|----------|
| `shop_id` | да | Идентификатор магазина (shopId) из ЛК ЮKassa |
| `secret_key` | да | Секретный ключ API из ЛК ЮKassa |
| `return_url` | нет | URL возврата по умолчанию (если клиент не передал свой) |

### `extra` (несекретное, `provider.extra`)

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
  "init_script_id": 10,
  "cb_script_id": 11
}
```

## Как это работает

**Инициализация** (`init`): скрипт шлёт
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

**Колбэк** (`callback`): в ЛК ЮKassa нужно настроить уведомление
`payment.succeeded` на URL:

```
https://<PUBLIC_URL>/api/v1/callback/payment/yookassa
```

Скрипт берёт `object.id` из уведомления и **перепроверяет** статус запросом
`GET https://api.yookassa.ru/v3/payments/{id}`. Платёж считается успешным при
`status == "succeeded"`. Наш внутренний `payment_id` восстанавливается из
`metadata.payment_id`.

## Проверка

1. Создать платёж: `POST /api/v1/user/purchases/create` с
   `{ "amount": 10, "provider": "yookassa", "target": "balance" }`.
2. Перейти по `public_data.pay_url`, оплатить тестовой картой ЮKassa.
3. Дождаться вебхука (или сымитировать: `POST .../callback/payment/yookassa`
   с телом `{"event":"payment.succeeded","object":{"id":"<id из ЮKassa>"}}`) —
   баланс пополнится, статус платежа станет `paid`.
