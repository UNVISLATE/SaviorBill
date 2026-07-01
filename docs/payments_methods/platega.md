# Platega

Официальная документация: <https://docs.platega.io/>. Базовый URL API —
`https://app.platega.io/`. Авторизация — заголовки `X-MerchantId` и `X-Secret`.

Скрипт: `examples/lua/payments/platega_payment.lua` (единый, action-driven:
create/callback/check/refund).

## Что заполнить

### `secrets` (шифруется, попадает в `payment.provider_data.secrets`)

| Поле | Обяз. | Описание |
|------|-------|----------|
| `merchant_id` | да | Значение заголовка `X-MerchantId` (из ЛК → Настройки) |
| `secret` | да | API-ключ, заголовок `X-Secret` |

### `extra` (несекретное, `payment.provider_data.extra`)

| Поле | Обяз. | По умолчанию | Описание |
|------|-------|--------------|----------|
| `payment_method` | нет | `2` | Числовой метод оплаты Platega |
| `success_url` | нет | — | URL успеха по умолчанию |
| `fail_url` | нет | — | URL неудачи |
| `status_url_tpl` | нет | `https://app.platega.io/transaction/%s` | Шаблон URL проверки статуса транзакции |
| `paid_statuses` | нет | `CONFIRMED,SUCCESS,PAID,COMPLETED` | «Успешные» статусы (через запятую) |

> `status_url_tpl` и `paid_statuses` вынесены в `extra`, чтобы подстроиться под
> точные значения вашего тарифа Platega без правки скрипта. Сверьте их с ЛК.

### Пример создания провайдера

```http
POST /api/v1/admin/purchases/providers
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "slug": "platega",
  "title": "Platega",
  "enabled": true,
  "currency": "RUB",
  "secrets": {
    "merchant_id": "29ef6fa6-0d2b-466c-9604-0363a30436cc",
    "secret": "iStHENoXjHdy78A4tGG3M6Tz..."
  },
  "extra": { "payment_method": 2 },
  "script_id": 12
}
```

## Как это работает

**Инициализация** (`action=create`): скрипт шлёт
`POST https://app.platega.io/transaction/process` с заголовками
`X-MerchantId` / `X-Secret` и телом:

```json
{
  "paymentMethod": 2,
  "paymentDetails": { "amount": 500, "currency": "RUB" },
  "description": "Payment #<id>",
  "return": "https://.../success",
  "failedUrl": "https://.../fail",
  "payload": "<наш id платежа>",
  "metadata": { "userId": "<id пользователя>" }
}
```

Из ответа берётся `redirect` → отдаётся клиенту как `pay_url`, а `transactionId`
сохраняется как `external_id`. Наш id платежа едет в `payload` — по нему
сверяемся в колбэке.

**Колбэк** (`action=callback`): URL вебхука в ЛК Platega:

```
https://<PUBLIC_URL>/api/v1/callback/payment/platega
```

Скрипт берёт `transactionId` и `payload` из тела уведомления
(`ctx.request.body`), затем **перепроверяет** статус запросом
`GET <status_url_tpl>` с мерчант-секретами. Платёж считается успешным, если
статус входит в `paid_statuses`. Действие `action=check` использует ту же
перепроверку (инициируется ядром), а `action=refund` шлёт
`POST https://app.platega.io/transaction/{id}/cancel`.

## Проверка

1. Создать платёж: `POST /api/v1/user/purchases/create` с
   `{ "amount": 100, "provider": "platega", "target": "balance" }`.
2. Перейти по `public_data.pay_url`, оплатить.
3. Дождаться вебхука Platega на `.../callback/payment/platega` — статус
   платежа станет `paid`, баланс пополнится.
