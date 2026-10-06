-- luaworker/src/billing.lua
-- Модуль взаимодействия Lua-скриптов с бэкендом SaviorBill

local cjson = require("cjson")
local httpc = require("httpc")

local M = {}

local function env(key, default)
  local v = os.getenv(key)
  if v == nil or v == "" then
    return default
  end
  return v
end

--- import_keys: импорт списка цифровых ключей в указанную услугу.
-- @param service: число (service_id) или строка (slug услуги)
-- @param keys: таблица-массив строк-ключей
-- @return таблица { ok = true, imported = N, duplicates = M, available_total = K }
--         или { ok = false, error = "сообщение об ошибке" }
function M.import_keys(service, keys)
  if type(service) ~= "number" and type(service) ~= "string" then
    return { ok = false, error = "import_keys: service must be an ID (number) or slug (string)" }
  end
  if type(keys) ~= "table" then
    return { ok = false, error = "import_keys: keys must be an array table of strings" }
  end

  local keys_list = {}
  for _, k in ipairs(keys) do
    if type(k) == "string" and k:match("%S") then
      keys_list[#keys_list + 1] = k
    end
  end

  if #keys_list == 0 then
    return { ok = false, error = "import_keys: keys list is empty" }
  end

  local billing_url = env("BILLING_URL", "http://billing:8000")
  local token = env("LUA_SERVICE_TOKEN", "dev-service-token")

  local payload = {
    service = service,
    keys = keys_list,
  }

  local req = {
    url = billing_url .. "/api/v1/internal/service-keys/import",
    method = "POST",
    headers = {
      ["Content-Type"] = "application/json",
      ["Authorization"] = "Bearer " .. token,
    },
    body = cjson.encode(payload),
    timeout = 10,
  }

  local resp = httpc.request(req)
  if not resp or not resp.ok then
    local err_msg = (resp and resp.error) or ("HTTP status " .. tostring(resp and resp.status))
    if resp and resp.body and #resp.body > 0 then
      local ok_json, parsed = pcall(cjson.decode, resp.body)
      if ok_json and parsed and parsed.detail then
        err_msg = tostring(parsed.detail)
      end
    end
    return { ok = false, error = "billing API error: " .. tostring(err_msg) }
  end

  local ok_decode, data = pcall(cjson.decode, resp.body)
  if not ok_decode or type(data) ~= "table" then
    return { ok = false, error = "invalid JSON response from billing" }
  end

  return {
    ok = true,
    imported = data.imported or 0,
    duplicates = data.duplicates or 0,
    available_total = data.available_total or 0,
  }
end

return M
