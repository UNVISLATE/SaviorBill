-- Демонстрационный платёжный скрипт (единый, action-driven).
--
-- Один скрипт обрабатывает все действия платежа. Ядро передаёт:
--   ctx = {
--     action  = "create" | "callback" | "check" | "refund",
--     user    = { id, login, email, ... },
--     payment = {
--       id, amount, currency, target, user_svc_id, external_id, return_url,
--       provider_data = { slug, secrets = {...}, extra = {...}, currency },
--     },
--     request = { method, ip, headers = {...}, query = {...}, body = {...} },
--               -- присутствует только для action = "callback"
--   }
-- Секреты платёжки — в ctx.payment.provider_data.secrets.
--
-- handle(ctx) обязан вернуть { public = {...}, private = {...} }:
--   create   → public.pay_url, private.external_id
--   callback → private.ok (подпись валидна), private.paid|failed,
--              private.payment_id | private.external_id (для сверки)
--   check    → private.ok, private.paid|failed, private.external_id
--   refund   → private.ok, private.refunded
--
-- ВАЖНО: callback (вебхук) — доверенный канал: скрипт сам проверяет подпись,
-- ядро полагается на его ответ. check инициируется ядром и должен
-- перепроверять статус запросом к API провайдера.

local M = {}

local function truthy(v)
  return v == true or v == "true" or v == "1" or v == 1
end

local function provider(ctx)
  local pay = ctx.payment or {}
  return pay.provider_data or {}
end

local function do_create(ctx)
  local pay = ctx.payment or {}
  local prov = provider(ctx)
  local settings = prov.secrets or {}
  -- Боевая интеграция: POST в API провайдера с ключами из settings.
  local ext = string.format("pay_%s_%d", tostring(pay.id or 0), os.time())
  local base = pay.return_url or (settings.pay_base or "https://example.test/pay")
  return {
    public = {
      pay_url = base .. "?txn=" .. ext,
      amount = pay.amount,
      currency = pay.currency,
    },
    private = { external_id = ext, provider = prov.slug },
  }
end

local function do_callback(ctx)
  local prov = provider(ctx)
  local settings = prov.secrets or {}
  local req = ctx.request or {}
  local body = req.body or {}

  local ok = false
  if settings.secret ~= nil and body.sign ~= nil then
    ok = (tostring(body.sign) == tostring(settings.secret))
  end
  return {
    public = {},
    private = {
      ok = ok,
      paid = truthy(body.success),
      failed = truthy(body.failed),
      payment_id = body.payment_id,
      external_id = body.external_id,
    },
  }
end

local function do_check(ctx)
  -- Боевая интеграция: запрос статуса к API провайдера по external_id.
  local pay = ctx.payment or {}
  return {
    public = {},
    private = { ok = true, paid = false, external_id = pay.external_id },
  }
end

local function do_refund(ctx)
  -- Боевая интеграция: POST на возврат в API провайдера.
  local pay = ctx.payment or {}
  return {
    public = {},
    private = { ok = true, refunded = true, external_id = pay.external_id },
  }
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
