-- YooKassa: единый action-driven платёжный скрипт.
--
-- Обрабатывает действия платежа по ctx.action:
--   create   — создание платежа (сценарий redirect), возвращает confirmation_url;
--   callback — вебхук payment.succeeded (тело в ctx.request.body);
--   check    — перепроверка статуса ядром (billing-loop / ручной recheck);
--   refund   — возврат средств.
--
-- Секреты (ctx.payment.provider_data.secrets):
--   shop_id     — идентификатор магазина ЮKassa;
--   secret_key  — секретный ключ ЮKassa;
--   return_url  — (опц.) URL возврата по умолчанию.
--
-- БЕЗОПАСНОСТЬ: тело вебхука ЮKassa не подписано — статус ВСЕГДА перепроверяется
-- отдельным server-to-server запросом к API ЮKassa (и в callback, и в check).
-- Это рекомендованный ЮKassa способ и надёжнее доверия телу запроса.

local M = {}

local B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
local function b64(data)
  local out = {}
  local len = #data
  local i = 1
  while i <= len do
    local a = string.byte(data, i) or 0
    local b = string.byte(data, i + 1)
    local c = string.byte(data, i + 2)
    local n = a * 65536 + (b or 0) * 256 + (c or 0)
    local c1 = math.floor(n / 262144) % 64
    local c2 = math.floor(n / 4096) % 64
    local c3 = math.floor(n / 64) % 64
    local c4 = n % 64
    out[#out + 1] = string.sub(B64, c1 + 1, c1 + 1)
    out[#out + 1] = string.sub(B64, c2 + 1, c2 + 1)
    out[#out + 1] = b and string.sub(B64, c3 + 1, c3 + 1) or "="
    out[#out + 1] = c and string.sub(B64, c4 + 1, c4 + 1) or "="
    i = i + 3
  end
  return table.concat(out)
end

local function secrets(ctx)
  return ((ctx.payment or {}).provider_data or {}).secrets or {}
end

local function auth_header(s)
  return "Basic " .. b64(tostring(s.shop_id) .. ":" .. tostring(s.secret_key))
end

-- Запрос статуса платежа у ЮKassa по его id.
local function fetch_status(s, ext)
  local resp = http({
    url = "https://api.yookassa.ru/v3/payments/" .. tostring(ext),
    method = "GET",
    headers = { ["authorization"] = auth_header(s) },
  })
  if not resp.ok or resp.status ~= 200 then
    return nil
  end
  return json.decode(resp.body) or {}
end

local function verify(ctx, ext)
  local s = secrets(ctx)
  if not ext or not s.shop_id or not s.secret_key then
    return { public = {}, private = { ok = false } }
  end
  local data = fetch_status(s, ext)
  if data == nil then
    return { public = {}, private = { ok = false } }
  end
  return {
    public = {},
    private = {
      ok = true,
      paid = (data.status == "succeeded"),
      failed = (data.status == "canceled"),
      payment_id = (data.metadata or {}).payment_id,
      external_id = data.id or ext,
      status = data.status,
    },
  }
end

local function do_create(ctx)
  local pay = ctx.payment or {}
  local s = secrets(ctx)
  assert(s.shop_id and s.secret_key, "yookassa: нужны shop_id и secret_key")

  local body = json.encode({
    amount = {
      value = string.format("%.2f", tonumber(pay.amount) or 0),
      currency = pay.currency or "RUB",
    },
    capture = true,
    confirmation = {
      type = "redirect",
      return_url = pay.return_url or s.return_url or "https://example.com/return",
    },
    description = "Payment #" .. tostring(pay.id),
    metadata = { payment_id = tostring(pay.id) },
  })

  local resp = http({
    url = "https://api.yookassa.ru/v3/payments",
    method = "POST",
    headers = {
      ["authorization"] = auth_header(s),
      ["idempotence-key"] = "sb-" .. tostring(pay.id) .. "-" .. tostring(os.time()),
      ["content-type"] = "application/json",
    },
    body = body,
  })
  if not resp.ok or (resp.status ~= 200 and resp.status ~= 201) then
    error("yookassa: создание платежа не удалось: "
      .. tostring(resp.status) .. " " .. tostring(resp.body))
  end
  local data = json.decode(resp.body)
  return {
    public = { pay_url = (data.confirmation or {}).confirmation_url },
    private = { external_id = data.id, status = data.status },
  }
end

local function do_callback(ctx)
  local body = (ctx.request or {}).body or {}
  local obj = body.object or {}
  local ext = obj.id or body.external_id or body.id
  return verify(ctx, ext)
end

local function do_check(ctx)
  return verify(ctx, (ctx.payment or {}).external_id)
end

local function do_refund(ctx)
  local pay = ctx.payment or {}
  local s = secrets(ctx)
  assert(s.shop_id and s.secret_key, "yookassa: нужны shop_id и secret_key")
  local body = json.encode({
    payment_id = tostring(pay.external_id),
    amount = {
      value = string.format("%.2f", tonumber(pay.amount) or 0),
      currency = pay.currency or "RUB",
    },
  })
  local resp = http({
    url = "https://api.yookassa.ru/v3/refunds",
    method = "POST",
    headers = {
      ["authorization"] = auth_header(s),
      ["idempotence-key"] = "sb-rf-" .. tostring(pay.id) .. "-" .. tostring(os.time()),
      ["content-type"] = "application/json",
    },
    body = body,
  })
  local ok = resp.ok and (resp.status == 200 or resp.status == 201)
  local data = ok and (json.decode(resp.body) or {}) or {}
  return {
    public = {},
    private = { ok = ok, refunded = (data.status == "succeeded"), external_id = data.id },
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
