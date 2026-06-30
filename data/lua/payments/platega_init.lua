-- Platega: init-скрипт (создание транзакции, /transaction/process).
--
-- Секреты провайдера (provider.settings, шифруются в БД):
--   merchant_id — X-MerchantId;
--   secret      — X-Secret (API-ключ).
-- Доп. параметры (provider.extra, не секретные):
--   payment_method — числовой метод оплаты Platega (по умолчанию 2);
--   success_url    — (опц.) URL успеха по умолчанию;
--   fail_url       — (опц.) URL неудачи.
-- Контекст: ctx.payment = { id, amount, currency, return_url }, ctx.user = { id }.
-- Возврат: public.pay_url — redirect Platega; private.external_id — transactionId.

local M = {}

function M.handle(ctx)
  local pay = ctx.payment or {}
  local prov = ctx.provider or {}
  local s = prov.settings or {}
  local extra = prov.extra or {}
  assert(s.merchant_id and s.secret, "platega: нужны merchant_id и secret")

  local body = json.encode({
    paymentMethod = tonumber(extra.payment_method) or 2,
    paymentDetails = {
      amount = tonumber(pay.amount) or 0,
      currency = pay.currency or "RUB",
    },
    description = "Payment #" .. tostring(pay.id),
    ["return"] = pay.return_url or extra.success_url or "https://example.com/success",
    failedUrl = extra.fail_url or "https://example.com/fail",
    -- payload несёт наш внутренний id платежа — по нему сверяем в callback.
    payload = tostring(pay.id),
    metadata = { userId = tostring((ctx.user or {}).id or "") },
  })

  local resp = http({
    url = "https://app.platega.io/transaction/process",
    method = "POST",
    headers = {
      ["x-merchantid"] = tostring(s.merchant_id),
      ["x-secret"] = tostring(s.secret),
      ["content-type"] = "application/json",
    },
    body = body,
  })
  if not resp.ok or (resp.status ~= 200 and resp.status ~= 201) then
    error("platega: создание транзакции не удалось: "
      .. tostring(resp.status) .. " " .. tostring(resp.body))
  end

  local data = json.decode(resp.body)
  return {
    public = { pay_url = data.redirect },
    private = { external_id = data.transactionId, status = data.status },
  }
end

return M
