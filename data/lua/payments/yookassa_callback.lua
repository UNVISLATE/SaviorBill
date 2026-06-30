-- YooKassa: callback-скрипт (вебхук payment.succeeded / возврат).
--
-- Секреты провайдера (provider.settings): shop_id, secret_key.
-- Контекст: ctx.request — тело вебхука ЮKassa { event, object = { id, status,
--   metadata } } и/или query success/fail url.
--
-- БЕЗОПАСНОСТЬ: тело вебхука НЕ доверяется напрямую. Статус платежа
-- перепроверяется отдельным запросом к API ЮKassa (server-to-server). Это
-- надёжнее проверки подписи и защищает от подделки уведомления.
-- Возврат private: ok (запрос валиден), paid (succeeded), payment_id (наш id из
-- metadata), external_id (id платежа в ЮKassa), status.

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

function M.handle(ctx)
  local s = (ctx.provider or {}).settings or {}
  local req = ctx.request or {}
  local obj = req.object or {}
  local ext = obj.id or req.external_id or req.id
  if not ext or not s.shop_id or not s.secret_key then
    return { public = {}, private = { ok = false } }
  end

  -- Перепроверяем статус напрямую у ЮKassa.
  local auth = "Basic " .. b64(tostring(s.shop_id) .. ":" .. tostring(s.secret_key))
  local resp = http({
    url = "https://api.yookassa.ru/v3/payments/" .. tostring(ext),
    method = "GET",
    headers = { ["authorization"] = auth },
  })
  if not resp.ok or resp.status ~= 200 then
    return { public = {}, private = { ok = false } }
  end

  local data = json.decode(resp.body) or {}
  local paid = (data.status == "succeeded")
  local pid = (data.metadata or {}).payment_id

  return {
    public = {},
    private = {
      ok = true,
      paid = paid,
      payment_id = pid,
      external_id = data.id or ext,
      status = data.status,
    },
  }
end

return M
