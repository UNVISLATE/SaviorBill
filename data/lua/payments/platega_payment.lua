-- Platega: единый action-driven платёжный скрипт.
--
-- Обрабатывает действия платежа по ctx.action:
--   create   — создание транзакции (/transaction/process), возвращает redirect;
--   callback — вебхук статуса транзакции (тело в ctx.request.body);
--   check    — перепроверка статуса ядром (billing-loop / ручной recheck);
--   refund   — отмена/возврат транзакции.
--
-- Секреты (ctx.payment.provider_data.secrets): merchant_id, secret.
-- Доп. параметры (ctx.payment.provider_data.extra, не секретные):
--   payment_method — числовой метод оплаты Platega (по умолчанию 2);
--   success_url/fail_url — (опц.) URL успеха/неудачи по умолчанию;
--   status_url_tpl — шаблон URL статуса ("https://app.platega.io/transaction/%s");
--   paid_statuses  — успешные статусы через запятую
--                    (по умолчанию "CONFIRMED,SUCCESS,PAID,COMPLETED").
--
-- БЕЗОПАСНОСТЬ: статус из вебхука не доверяется напрямую — он ВСЕГДА
-- перепроверяется запросом к API Platega с merchant-секретами.

local M = {}

local function secrets(ctx)
  return ((ctx.payment or {}).provider_data or {}).secrets or {}
end

local function extra(ctx)
  return ((ctx.payment or {}).provider_data or {}).extra or {}
end

local function is_paid(status, ex)
  local ok_statuses = ex.paid_statuses or "CONFIRMED,SUCCESS,PAID,COMPLETED"
  for st in string.gmatch(ok_statuses, "[^,]+") do
    if status == st then
      return true
    end
  end
  return false
end

-- Перепроверка статуса транзакции у Platega.
local function verify(ctx, txn, pid)
  local s = secrets(ctx)
  local ex = extra(ctx)
  if not txn or not s.merchant_id or not s.secret then
    return { public = {}, private = { ok = false } }
  end
  local tpl = ex.status_url_tpl or "https://app.platega.io/transaction/%s"
  local resp = http({
    url = string.format(tpl, tostring(txn)),
    method = "GET",
    headers = {
      ["x-merchantid"] = tostring(s.merchant_id),
      ["x-secret"] = tostring(s.secret),
    },
  })
  if not resp.ok or resp.status ~= 200 then
    return { public = {}, private = { ok = false } }
  end
  local data = json.decode(resp.body) or {}
  local status = data.status
  return {
    public = {},
    private = {
      ok = true,
      paid = is_paid(status, ex),
      failed = (status == "CANCELED" or status == "FAILED" or status == "DECLINED"),
      payment_id = pid,
      external_id = txn,
      status = status,
    },
  }
end

local function do_create(ctx)
  local pay = ctx.payment or {}
  local s = secrets(ctx)
  local ex = extra(ctx)
  assert(s.merchant_id and s.secret, "platega: нужны merchant_id и secret")

  local body = json.encode({
    paymentMethod = tonumber(ex.payment_method) or 2,
    paymentDetails = {
      amount = tonumber(pay.amount) or 0,
      currency = pay.currency or "RUB",
    },
    description = "Payment #" .. tostring(pay.id),
    ["return"] = pay.return_url or ex.success_url or "https://example.com/success",
    failedUrl = ex.fail_url or "https://example.com/fail",
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

local function do_callback(ctx)
  local body = (ctx.request or {}).body or {}
  local txn = body.transactionId or body.id or body.external_id
  local pid = body.payload or body.payment_id
  return verify(ctx, txn, pid)
end

local function do_check(ctx)
  return verify(ctx, (ctx.payment or {}).external_id, (ctx.payment or {}).id)
end

local function do_refund(ctx)
  local pay = ctx.payment or {}
  local s = secrets(ctx)
  if not pay.external_id or not s.merchant_id or not s.secret then
    return { public = {}, private = { ok = false } }
  end
  local resp = http({
    url = "https://app.platega.io/transaction/" .. tostring(pay.external_id) .. "/cancel",
    method = "POST",
    headers = {
      ["x-merchantid"] = tostring(s.merchant_id),
      ["x-secret"] = tostring(s.secret),
    },
  })
  local ok = resp.ok and (resp.status == 200 or resp.status == 201)
  return { public = {}, private = { ok = ok, refunded = ok, external_id = pay.external_id } }
end

local _DISPATCH = {
  create = do_create,
  callback = do_callback,
  check = do_check,
  refund = do_refund,
}

function M.handle(ctx)
  local fn = _DISPATCH[ctx.action or "create"]
  if fn == nil then
    return { public = {}, private = { ok = false, error = "unknown action" } }
  end
  return fn(ctx)
end

return M
