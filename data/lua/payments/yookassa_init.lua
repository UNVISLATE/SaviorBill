-- YooKassa: init-скрипт (создание платежа, сценарий redirect).
--
-- Секреты провайдера (provider.settings, шифруются в БД):
--   shop_id     — идентификатор магазина ЮKassa;
--   secret_key  — секретный ключ ЮKassa;
--   return_url  — (опц.) URL возврата по умолчанию.
-- Контекст: ctx.payment = { id, amount, currency, return_url }.
-- Возврат: public.pay_url — confirmation_url ЮKassa; private.external_id — id
-- платежа в ЮKassa (для сверки в callback-скрипте).

local M = {}

-- Чистый Lua base64-энкодер (для заголовка Basic auth, без внешних модулей).
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

function M.handle(ctx)
  local pay = ctx.payment or {}
  local s = (ctx.provider or {}).settings or {}
  assert(s.shop_id and s.secret_key, "yookassa: нужны shop_id и secret_key")

  local auth = "Basic " .. b64(tostring(s.shop_id) .. ":" .. tostring(s.secret_key))
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
      ["authorization"] = auth,
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

return M
